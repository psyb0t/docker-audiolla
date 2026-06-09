"""End-to-end test for ``POST /v1/audio/repair``.

Repair audio: interpolate clipped samples (declip) and/or remove mains
hum (dehum). At least one of declip/dehum must be true.
"""

from __future__ import annotations

import httpx

from .helpers import assert_wav


def test_repair_declip_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Default params (declip=True) return a valid WAV."""
    r = client.post(
        "/v1/audio/repair",
        json={
            "file_path": staged_audio,
            "output_path": "out/repair.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_repair_dehum(client: httpx.Client, staged_audio: str) -> None:
    """dehum=True with hum_freq=50 (EU mains) → 200 valid WAV."""
    r = client.post(
        "/v1/audio/repair",
        json={
            "file_path": staged_audio,
            "declip": False,
            "dehum": True,
            "hum_freq": 50,
            "output_path": "out/repair_dehum.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_repair_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    r = client.post(
        "/v1/audio/repair",
        json={
            "file_path": staged_audio,
            "output_path": "repair_test/fixed.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "repair_test/fixed.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_repair_both_false_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """declip=False and dehum=False → no-op rejected, 400 (or 422)."""
    r = client.post(
        "/v1/audio/repair",
        json={
            "file_path": staged_audio,
            "declip": False,
            "dehum": False,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text
