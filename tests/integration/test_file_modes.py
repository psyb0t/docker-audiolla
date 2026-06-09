"""End-to-end tests for the input/output mode contract.

Every audio endpoint accepts either ``file_path`` (staged) or ``file_url``
(remote, subject to allowlist) for input, and ``output_path`` (staged) or
``output_url`` (PUT-on-success) for output. These tests use
``/v1/audio/transform`` because sox-transform is CPU-light and the
endpoint exposes the full xor contract.

The file_url + output_url tests need ``AUDIOLLA_FETCH_MODE=allowlist`` +
``AUDIOLLA_FETCH_HOSTS`` set on the harness container; they're skipped
when the harness was started with the default fetch policy.
"""

from __future__ import annotations

import os
import secrets

import httpx
import pytest

pytestmark = pytest.mark.engine("sox-transform")


_FETCH_MODE = os.environ.get("AUDIOLLA_FETCH_MODE", "disabled").lower()
_LOOPBACK_ALLOWED = (
    _FETCH_MODE == "allowlist"
    and "127.0.0.1" in os.environ.get("AUDIOLLA_FETCH_HOSTS", "")
    and os.environ.get("AUDIOLLA_FETCH_ALLOW_PRIVATE", "").lower() in ("1", "true")
)


_NEEDS_FETCH = pytest.mark.skipif(
    not _LOOPBACK_ALLOWED,
    reason="needs AUDIOLLA_FETCH_MODE=allowlist + 127.0.0.1 + ALLOW_PRIVATE=true",
)


def test_transform_with_file_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """file_path input + output_path → 200 with the staged path in the response."""
    dest = f"modes/out-fp-{secrets.token_hex(4)}.wav"
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "output_format": "wav",
            "operations": [{"op": "gain", "params": {"db": -1}}],
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == dest


def test_file_path_missing_404(client: httpx.Client) -> None:
    """file_path that doesn't exist on staging → 404."""
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": "nope/does/not/exist.wav",
            "operations": [{"op": "gain", "params": {"db": 0}}],
            "output_path": f"modes/out-{secrets.token_hex(4)}.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_transform_with_output_path_writes_riff(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_path stages a real RIFF/WAVE — round-trip via /v1/files."""
    dest = f"modes/out-{secrets.token_hex(4)}.wav"
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "output_format": "wav",
            "operations": [{"op": "gain", "params": {"db": -1}}],
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == dest
    assert "size" in body

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert fetched.content[:4] == b"RIFF"


def test_output_path_traversal_rejected(
    client: httpx.Client, staged_audio: str,
) -> None:
    """`../escape.wav` in output_path → 400 (path-safety rejection)."""
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "operations": [{"op": "gain", "params": {"db": 0}}],
            "output_path": "../escape.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_output_path_and_url_mutually_exclusive(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Both output_path AND output_url set → 400 (handler-level xor)."""
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "operations": [{"op": "gain", "params": {"db": 0}}],
            "output_path": f"modes/x-{secrets.token_hex(4)}.wav",
            "output_url": "http://127.0.0.1:8000/v1/files/y.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_input_path_and_url_mutually_exclusive(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Both file_path AND file_url set → 400 (handler-level xor)."""
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "file_url": "https://example.com/x.wav",
            "operations": [{"op": "gain", "params": {"db": 0}}],
            "output_path": f"modes/bad-{secrets.token_hex(4)}.wav",
        },
    )
    assert r.status_code == 400, r.text


@_NEEDS_FETCH
def test_file_url_loopback_fetch(
    client: httpx.Client, audiolla_url: str, staged_audio: str,
) -> None:
    """file_url pointing at the harness's own /v1/files → 200 (loopback fetch)."""
    target = f"{audiolla_url}/v1/files/{staged_audio}"
    dest = f"modes/out-furl-{secrets.token_hex(4)}.wav"
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_url": target,
            "output_format": "wav",
            "operations": [{"op": "gain", "params": {"db": 0}}],
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    assert "path" in r.json()


@_NEEDS_FETCH
def test_file_url_outside_allowlist_400(client: httpx.Client) -> None:
    """A file_url whose host isn't in the allowlist → 400 mentioning allowlist."""
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_url": "https://evil.example.com/x.wav",
            "operations": [{"op": "gain", "params": {"db": 0}}],
            "output_path": f"modes/evil-{secrets.token_hex(4)}.wav",
        },
    )
    assert r.status_code == 400, r.text
    assert "allowlist" in r.text.lower()


@_NEEDS_FETCH
def test_output_url_loopback_put(
    client: httpx.Client, audiolla_url: str, staged_audio: str,
) -> None:
    """output_url pointing at the harness's own /v1/files staged the result."""
    dest_path = f"modes/out-via-url-{secrets.token_hex(4)}.wav"
    target = f"{audiolla_url}/v1/files/{dest_path}"
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "output_format": "wav",
            "operations": [{"op": "gain", "params": {"db": 0}}],
            "output_url": target,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "url" in body
    assert "size" in body

    fetched = client.get(f"/v1/files/{dest_path}")
    assert fetched.status_code == 200
    assert len(fetched.content) > 0
