"""Unit tests for audiolla.fetch — host pattern matching and policy
validation. The actual HTTP I/O paths (fetch_to_bytes, upload_bytes) are
covered by the integration suite — they need a live server."""

from __future__ import annotations

import os
import sys

import pytest


# `audiolla.config` parses env at import time; tests that need a different
# policy reimport via importlib. The default policy is `disabled`.

_RELOADED_MODULES = ("audiolla.fetch", "audiolla.config")


@pytest.fixture(autouse=True)
def _restore_modules():
    """Snapshot sys.modules + env before each test; restore after. Without
    this, the module reloads in `_reload_config_with` would detach the
    config / fetch references that OTHER test modules (input_resolver,
    server) captured at their import time."""
    saved_mods = {k: sys.modules[k] for k in _RELOADED_MODULES if k in sys.modules}
    saved_env = {
        k: os.environ.get(k)
        for k in (
            "AUDIOLLA_FETCH_MODE", "AUDIOLLA_FETCH_HOSTS",
            "AUDIOLLA_FETCH_SCHEMES", "AUDIOLLA_FETCH_TIMEOUT",
            "AUDIOLLA_FETCH_ALLOW_PRIVATE", "AUDIOLLA_FETCH_MAX_REDIRECTS",
        )
    }
    yield
    for k in _RELOADED_MODULES:
        if k in saved_mods:
            sys.modules[k] = saved_mods[k]
        else:
            sys.modules.pop(k, None)
    for k, v in saved_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def _reload_config_with(env: dict[str, str]):
    """Reset env keys and reimport config + fetch under the new env."""
    import importlib

    for k in [
        "AUDIOLLA_FETCH_MODE", "AUDIOLLA_FETCH_HOSTS",
        "AUDIOLLA_FETCH_SCHEMES", "AUDIOLLA_FETCH_TIMEOUT",
        "AUDIOLLA_FETCH_ALLOW_PRIVATE", "AUDIOLLA_FETCH_MAX_REDIRECTS",
    ]:
        os.environ.pop(k, None)
    os.environ.update(env)
    for mod in _RELOADED_MODULES:
        if mod in sys.modules:
            del sys.modules[mod]
    import audiolla.config  # noqa: F401
    return importlib.import_module("audiolla.fetch")


# ── host_matches ─────────────────────────────────────────────────────────────

def test_host_matches_exact():
    from audiolla.fetch import host_matches
    assert host_matches("foo.example.com", ["foo.example.com"])
    assert not host_matches("bar.example.com", ["foo.example.com"])


def test_host_matches_wildcard_subdomain():
    from audiolla.fetch import host_matches
    assert host_matches("bucket.s3.amazonaws.com", ["*.s3.amazonaws.com"])
    assert host_matches(
        "abc.def.s3.amazonaws.com", ["*.s3.amazonaws.com"]
    )


def test_host_matches_wildcard_does_not_match_bare_suffix():
    """`*.s3.amazonaws.com` must NOT match `s3.amazonaws.com` itself —
    that needs its own entry. This is the same rule cert SANs use."""
    from audiolla.fetch import host_matches
    assert not host_matches("s3.amazonaws.com", ["*.s3.amazonaws.com"])


def test_host_matches_case_insensitive():
    from audiolla.fetch import host_matches
    assert host_matches("FOO.s3.amazonaws.com", ["foo.s3.amazonaws.com"])
    assert host_matches("foo.S3.AMAZONAWS.com", ["*.s3.amazonaws.com"])


def test_host_matches_empty_patterns():
    from audiolla.fetch import host_matches
    assert not host_matches("foo.example.com", [])
    assert not host_matches("foo.example.com", ["", "  "])


def test_host_matches_multiple_patterns():
    from audiolla.fetch import host_matches
    pats = ["bucket.s3.amazonaws.com", "*.r2.cloudflarestorage.com"]
    assert host_matches("bucket.s3.amazonaws.com", pats)
    assert host_matches("xyz.r2.cloudflarestorage.com", pats)
    assert not host_matches("evil.com", pats)


# ── _is_unsafe_ip ────────────────────────────────────────────────────────────

def test_unsafe_ip_loopback():
    from audiolla.fetch import _is_unsafe_ip
    assert _is_unsafe_ip("127.0.0.1")
    assert _is_unsafe_ip("::1")


def test_unsafe_ip_private_v4():
    from audiolla.fetch import _is_unsafe_ip
    assert _is_unsafe_ip("10.0.0.1")
    assert _is_unsafe_ip("192.168.1.1")
    assert _is_unsafe_ip("172.16.0.1")


def test_unsafe_ip_link_local():
    from audiolla.fetch import _is_unsafe_ip
    assert _is_unsafe_ip("169.254.169.254")  # AWS metadata
    assert _is_unsafe_ip("fe80::1")


def test_unsafe_ip_public():
    from audiolla.fetch import _is_unsafe_ip
    assert not _is_unsafe_ip("8.8.8.8")
    assert not _is_unsafe_ip("1.1.1.1")
    assert not _is_unsafe_ip("2001:4860:4860::8888")


def test_unsafe_ip_garbage():
    """Anything that isn't a parseable address is treated as unsafe —
    fail closed."""
    from audiolla.fetch import _is_unsafe_ip
    assert _is_unsafe_ip("not-an-ip")
    assert _is_unsafe_ip("")


# ── validate_url policy ──────────────────────────────────────────────────────

def test_validate_url_rejects_when_disabled():
    fetch = _reload_config_with({"AUDIOLLA_FETCH_MODE": "disabled"})
    with pytest.raises(fetch.FetchError, match="disabled"):
        fetch.validate_url("https://example.com/x")


def test_validate_url_allowlist_accepts_match():
    fetch = _reload_config_with({
        "AUDIOLLA_FETCH_MODE": "allowlist",
        "AUDIOLLA_FETCH_HOSTS": "*.s3.amazonaws.com",
        "AUDIOLLA_FETCH_ALLOW_PRIVATE": "true",
    })
    # Allow private to avoid DNS-resolving real S3 in unit tests; the
    # policy decision under test is the allowlist match.
    scheme, host = fetch.validate_url(
        "https://bucket.s3.amazonaws.com/track.wav"
    )
    assert scheme == "https"
    assert host == "bucket.s3.amazonaws.com"


def test_validate_url_allowlist_rejects_other_host():
    fetch = _reload_config_with({
        "AUDIOLLA_FETCH_MODE": "allowlist",
        "AUDIOLLA_FETCH_HOSTS": "*.s3.amazonaws.com",
        "AUDIOLLA_FETCH_ALLOW_PRIVATE": "true",
    })
    with pytest.raises(fetch.FetchError, match="allowlist"):
        fetch.validate_url("https://evil.com/x")


def test_validate_url_denylist_rejects_match():
    fetch = _reload_config_with({
        "AUDIOLLA_FETCH_MODE": "denylist",
        "AUDIOLLA_FETCH_HOSTS": "*.internal,localhost",
        "AUDIOLLA_FETCH_ALLOW_PRIVATE": "true",
    })
    with pytest.raises(fetch.FetchError, match="denylist"):
        fetch.validate_url("https://api.internal/x")


def test_validate_url_denylist_accepts_non_match():
    fetch = _reload_config_with({
        "AUDIOLLA_FETCH_MODE": "denylist",
        "AUDIOLLA_FETCH_HOSTS": "*.internal,localhost",
        "AUDIOLLA_FETCH_ALLOW_PRIVATE": "true",
    })
    scheme, host = fetch.validate_url("https://example.com/x")
    assert scheme == "https"
    assert host == "example.com"


def test_validate_url_rejects_bad_scheme():
    fetch = _reload_config_with({
        "AUDIOLLA_FETCH_MODE": "denylist",  # permissive
        "AUDIOLLA_FETCH_HOSTS": "",
        "AUDIOLLA_FETCH_SCHEMES": "https",
        "AUDIOLLA_FETCH_ALLOW_PRIVATE": "true",
    })
    with pytest.raises(fetch.FetchError, match="scheme"):
        fetch.validate_url("file:///etc/passwd")
    with pytest.raises(fetch.FetchError, match="scheme"):
        fetch.validate_url("http://example.com/x")


def test_validate_url_rejects_missing_host():
    fetch = _reload_config_with({
        "AUDIOLLA_FETCH_MODE": "denylist",
        "AUDIOLLA_FETCH_HOSTS": "",
        "AUDIOLLA_FETCH_ALLOW_PRIVATE": "true",
    })
    with pytest.raises(fetch.FetchError, match="scheme and host"):
        fetch.validate_url("https://")


def test_validate_url_rejects_private_ip_resolution(monkeypatch):
    fetch = _reload_config_with({
        "AUDIOLLA_FETCH_MODE": "denylist",
        "AUDIOLLA_FETCH_HOSTS": "",
        "AUDIOLLA_FETCH_ALLOW_PRIVATE": "false",
    })
    # Mock DNS to return a loopback IP for an otherwise-public host.
    import socket
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "",
             ("127.0.0.1", 0))
        ],
    )
    with pytest.raises(fetch.FetchError, match="private/loopback"):
        fetch.validate_url("https://evil-dns.example.com/x")


def test_validate_url_allows_private_when_opted_in(monkeypatch):
    fetch = _reload_config_with({
        "AUDIOLLA_FETCH_MODE": "denylist",
        "AUDIOLLA_FETCH_HOSTS": "",
        "AUDIOLLA_FETCH_ALLOW_PRIVATE": "true",
    })
    import socket
    monkeypatch.setattr(
        socket, "getaddrinfo",
        lambda host, port, **kw: [
            (socket.AF_INET, socket.SOCK_STREAM, 0, "",
             ("10.0.0.5", 0))
        ],
    )
    scheme, host = fetch.validate_url("https://internal-s3.example.net/x")
    assert host == "internal-s3.example.net"


# ── config bootstrap rejects bad combos ──────────────────────────────────────

def test_allowlist_without_hosts_is_rejected():
    """`AUDIOLLA_FETCH_MODE=allowlist` with no hosts is meaningless — fail
    fast at config-load rather than silently letting every URL through
    because of an empty allowlist."""
    with pytest.raises(ValueError, match="non-empty"):
        _reload_config_with({
            "AUDIOLLA_FETCH_MODE": "allowlist",
            "AUDIOLLA_FETCH_HOSTS": "",
        })


def test_bad_mode_is_rejected():
    with pytest.raises(ValueError, match="must be"):
        _reload_config_with({"AUDIOLLA_FETCH_MODE": "whatever"})


def test_bad_scheme_is_rejected():
    with pytest.raises(ValueError, match="unsupported scheme"):
        _reload_config_with({
            "AUDIOLLA_FETCH_MODE": "denylist",
            "AUDIOLLA_FETCH_HOSTS": "",
            "AUDIOLLA_FETCH_SCHEMES": "ftp",
        })
