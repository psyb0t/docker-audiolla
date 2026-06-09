"""End-to-end tests for ``POST /v1/audio/fingerprint``.

Chromaprint audio fingerprint via fpcalc. JSON-only response with
duration + fingerprint (base64-encoded string).
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.engine("audio-fingerprint")


def test_fingerprint_returns_string(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response has numeric duration + non-trivial fingerprint string."""
    r = client.post("/v1/audio/fingerprint", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["duration"], (int, float))
    assert isinstance(body["fingerprint"], str)
    assert len(body["fingerprint"]) > 20


def test_fingerprint_is_deterministic(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Same input → identical fingerprint across calls."""
    r1 = client.post("/v1/audio/fingerprint", json={"file_path": staged_audio})
    r2 = client.post("/v1/audio/fingerprint", json={"file_path": staged_audio})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["fingerprint"] == r2.json()["fingerprint"]


def test_fingerprint_return_raw(
    client: httpx.Client, staged_audio: str,
) -> None:
    """return_raw=true adds fingerprint_raw (list of ints) to the response."""
    r = client.post(
        "/v1/audio/fingerprint",
        json={"file_path": staged_audio, "return_raw": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    raw = body.get("fingerprint_raw")
    assert isinstance(raw, list)
    assert len(raw) > 0
    assert isinstance(raw[0], (int, float))


def test_fingerprint_via_file_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """A freshly PUT'd file is reachable as file_path."""
    # staged_audio is already PUT to /v1/files/uploads/test-*.wav, so this
    # is essentially the same as the basic test but kept for parity with
    # the bash source.
    r = client.post("/v1/audio/fingerprint", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["fingerprint"], str)


def test_fingerprint_analyze_seconds(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Short scan window produces a fingerprint no longer than the full one."""
    full = client.post(
        "/v1/audio/fingerprint",
        json={"file_path": staged_audio},
    )
    short = client.post(
        "/v1/audio/fingerprint",
        json={"file_path": staged_audio, "analyze_seconds": 3},
    )
    assert full.status_code == 200 and short.status_code == 200
    fp_full = full.json()["fingerprint"]
    fp_short = short.json()["fingerprint"]
    assert len(fp_short) > 0
    assert len(fp_short) <= len(fp_full)
