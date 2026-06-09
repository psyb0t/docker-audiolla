"""End-to-end test for ``POST /v1/audio/sidechain-duck``.

Duck primary audio when trigger audio is loud (voiceover-over-music
effect). ffmpeg-only; no engine slug required.
"""

from __future__ import annotations

import httpx

from .helpers import assert_mp3, assert_wav


def test_sidechain_duck_returns_wav(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """Primary + trigger → 200 with valid WAV at staged path."""
    r = client.post(
        "/v1/audio/sidechain-duck",
        json={
            "file_path": staged_audio,
            "trigger_file_path": staged_reference,
            "output_path": "out/duck.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_sidechain_duck_custom_params(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """Custom threshold_db, ratio, attack_ms, release_ms accepted → 200."""
    r = client.post(
        "/v1/audio/sidechain-duck",
        json={
            "file_path": staged_audio,
            "trigger_file_path": staged_reference,
            "threshold_db": -30.0,
            "ratio": 8.0,
            "attack_ms": 5.0,
            "release_ms": 100.0,
            "output_path": "out/duck_custom.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_sidechain_duck_output_format_mp3(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    r = client.post(
        "/v1/audio/sidechain-duck",
        json={
            "file_path": staged_audio,
            "trigger_file_path": staged_reference,
            "output_format": "mp3",
            "output_path": "out/duck.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_sidechain_duck_staged_trigger(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """trigger_file_path may itself point to a previously-staged file."""
    trim_r = client.post(
        "/v1/audio/trim",
        json={
            "file_path": staged_reference,
            "start_sec": 0.0,
            "end_sec": 4.0,
            "output_path": "duck/trigger.wav",
        },
    )
    assert trim_r.status_code == 200, trim_r.text

    r = client.post(
        "/v1/audio/sidechain-duck",
        json={
            "file_path": staged_audio,
            "trigger_file_path": "duck/trigger.wav",
            "output_path": "out/duck_staged_trigger.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_sidechain_duck_missing_trigger_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing trigger_file_path / trigger_file_url → 400 (or 422)."""
    r = client.post(
        "/v1/audio/sidechain-duck",
        json={
            "file_path": staged_audio,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_sidechain_duck_missing_primary_4xx(
    client: httpx.Client, staged_reference: str,
) -> None:
    """A non-existent primary file_path → 404 (or 400/422)."""
    r = client.post(
        "/v1/audio/sidechain-duck",
        json={
            "file_path": "no/such.wav",
            "trigger_file_path": staged_reference,
            "output_path": "out/missing.wav",
        },
    )
    assert r.status_code in (400, 404, 422, 500), r.text


def test_sidechain_duck_output_path(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    r = client.post(
        "/v1/audio/sidechain-duck",
        json={
            "file_path": staged_audio,
            "trigger_file_path": staged_reference,
            "output_path": "duck/out.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "duck/out.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)
