"""SSRF-safe URL fetcher and presigned-URL uploader.

Used by the `file_url` / `output_url` input/output modes on the audio
endpoints. Policy is driven by AUDIOLLA_FETCH_MODE (disabled / allowlist /
denylist), AUDIOLLA_FETCH_HOSTS, AUDIOLLA_FETCH_SCHEMES.

Always-on protections (regardless of mode):
- DNS-resolve host before connect; reject private / loopback / link-local /
  reserved IPs unless AUDIOLLA_FETCH_ALLOW_PRIVATE=true.
- Redirects are *not* auto-followed by httpx — each Location is
  re-validated through the same policy before re-issuing.
- Hard request timeout (AUDIOLLA_FETCH_TIMEOUT, default 30s).
- Size cap equal to AUDIOLLA_MAX_UPLOAD_BYTES — body is streamed and the
  fetch is aborted as soon as the cap is exceeded.
- Every fetch / upload URL is logged at INFO.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse, urljoin

import httpx

from . import config


_log = logging.getLogger("audiolla.fetch")


class FetchError(Exception):
    """URL fetch / upload was refused by policy or failed mid-flight."""


def _is_unsafe_ip(addr: str) -> bool:
    """Return True if the address is private / loopback / link-local etc."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return True
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


def host_matches(host: str, patterns: list[str]) -> bool:
    """True if `host` matches any pattern. Patterns are exact lowercase
    hostnames or `*.suffix` (single leading wildcard label).
    """
    host = host.lower()
    for raw in patterns:
        pat = raw.strip().lower()
        if not pat:
            continue
        if pat == host:
            return True
        if pat.startswith("*."):
            suffix = pat[1:]  # ".s3.amazonaws.com"
            # `*.s3.amazonaws.com` matches `x.s3.amazonaws.com` but NOT
            # `s3.amazonaws.com` itself — that needs its own entry.
            if host.endswith(suffix) and len(host) > len(suffix):
                return True
    return False


def validate_url(url: str) -> tuple[str, str]:
    """Validate `url` against the configured fetch policy.

    Returns (scheme, host). Raises FetchError on any policy violation.
    Always-on protections (private IP check, scheme allowlist) apply even
    if the host/policy match is permissive.
    """
    if config.FETCH_MODE == "disabled":
        raise FetchError(
            "URL fetch/upload is disabled "
            "(AUDIOLLA_FETCH_MODE=disabled); use file/file_path instead"
        )
    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise FetchError(f"invalid URL: {exc}") from exc
    scheme = (parsed.scheme or "").lower()
    host = (parsed.hostname or "").lower()
    if not scheme or not host:
        raise FetchError(f"URL must include scheme and host: {url!r}")
    if scheme not in config.FETCH_SCHEMES:
        raise FetchError(
            f"scheme {scheme!r} not in AUDIOLLA_FETCH_SCHEMES="
            f"{config.FETCH_SCHEMES}"
        )

    if config.FETCH_MODE == "allowlist":
        if not host_matches(host, config.FETCH_HOSTS):
            raise FetchError(
                f"host {host!r} not in AUDIOLLA_FETCH_HOSTS allowlist"
            )
    elif config.FETCH_MODE == "denylist":
        if host_matches(host, config.FETCH_HOSTS):
            raise FetchError(
                f"host {host!r} matches AUDIOLLA_FETCH_HOSTS denylist"
            )

    if not config.FETCH_ALLOW_PRIVATE:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise FetchError(
                f"DNS resolution failed for {host!r}: {exc}"
            ) from exc
        for info in infos:
            addr = str(info[4][0])
            if _is_unsafe_ip(addr):
                raise FetchError(
                    f"host {host!r} resolves to private/loopback IP {addr}; "
                    "set AUDIOLLA_FETCH_ALLOW_PRIVATE=true to allow"
                )

    return scheme, host


async def fetch_to_bytes(url: str, max_bytes: int) -> tuple[bytes, str]:
    """Fetch `url` and return (data, suggested_filename).

    Streams the body; aborts when the cap is exceeded. Re-validates every
    redirect Location through `validate_url` before following.
    """
    validate_url(url)
    _log.info("fetch: GET %s (cap=%d)", url, max_bytes)
    timeout = httpx.Timeout(config.FETCH_TIMEOUT_SECONDS, connect=10.0)
    async with httpx.AsyncClient(
        timeout=timeout, follow_redirects=False
    ) as client:
        current = url
        for _ in range(max(0, config.FETCH_MAX_REDIRECTS) + 1):
            async with client.stream("GET", current) as resp:
                if 300 <= resp.status_code < 400:
                    loc = resp.headers.get("location")
                    if not loc:
                        raise FetchError(
                            f"redirect from {current!r} missing Location header"
                        )
                    next_url = urljoin(current, loc)
                    validate_url(next_url)
                    _log.info("fetch: redirect -> %s", next_url)
                    current = next_url
                    continue
                if resp.status_code != 200:
                    raise FetchError(
                        f"fetch failed: HTTP {resp.status_code} from {current!r}"
                    )
                buf = bytearray()
                async for chunk in resp.aiter_bytes():
                    buf.extend(chunk)
                    if len(buf) > max_bytes:
                        raise FetchError(
                            f"fetched body exceeds {max_bytes} bytes"
                        )
                parsed = urlparse(current)
                name = parsed.path.rsplit("/", 1)[-1] or "audio"
                # Strip query string artefacts that crept into the path.
                name = name.split("?", 1)[0].split("#", 1)[0] or "audio"
                return bytes(buf), name
        raise FetchError(
            f"too many redirects (>{config.FETCH_MAX_REDIRECTS})"
        )


async def upload_bytes(url: str, data: bytes, content_type: str) -> None:
    """PUT `data` to a presigned `url`. Policy applies to upload targets
    the same as to fetch sources — a hostile output_url can still SSRF.
    """
    validate_url(url)
    _log.info(
        "upload: PUT %s (%d bytes, content_type=%s)",
        url, len(data), content_type,
    )
    timeout = httpx.Timeout(config.FETCH_TIMEOUT_SECONDS, connect=10.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.put(
            url, content=data, headers={"Content-Type": content_type}
        )
    if resp.status_code not in (200, 201, 204):
        raise FetchError(
            f"upload failed: HTTP {resp.status_code} from {url!r}"
        )
