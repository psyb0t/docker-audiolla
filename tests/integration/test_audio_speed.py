"""End-to-end test for ``POST /v1/audio/speed``.

Change playback speed without pitch shift via ffmpeg atempo. Range
0.1–10.0; speed=2.0 doubles, speed=0.5 halves.
"""

from __future__ import annotations

import httpx

from .helpers import assert_mp3, assert_wav


def test_speed_returns_wav(client: httpx.Client, staged_audio: str) -> None:
    """speed=2.0 returns a valid WAV."""
    r = client.post(
        "/v1/audio/speed",
        json={
            "file_path": staged_audio,
            "speed": 2.0,
            "output_path": "out/speed2.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_speed_double_halves_duration(
    client: httpx.Client, staged_audio: str,
) -> None:
    """speed=2.0 → output duration < 75% of source."""
    src = client.post("/v1/audio/info", json={"file_path": staged_audio})
    src_dur = float(src.json()["duration_sec"])

    r = client.post(
        "/v1/audio/speed",
        json={
            "file_path": staged_audio,
            "speed": 2.0,
            "output_path": "out/speed_dur.wav",
        },
    )
    assert r.status_code == 200, r.text

    info = client.post(
        "/v1/audio/info", json={"file_path": "out/speed_dur.wav"},
    )
    assert float(info.json()["duration_sec"]) < src_dur * 0.75


def test_speed_half(client: httpx.Client, staged_audio: str) -> None:
    """speed=0.5 is accepted → 200."""
    r = client.post(
        "/v1/audio/speed",
        json={
            "file_path": staged_audio,
            "speed": 0.5,
            "output_path": "out/speed_half.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_speed_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    r = client.post(
        "/v1/audio/speed",
        json={
            "file_path": staged_audio,
            "speed": 1.5,
            "output_format": "mp3",
            "output_path": "out/speed.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_speed_out_of_range_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """speed=20.0 is outside [0.1, 10.0] → 400 (or 422)."""
    r = client.post(
        "/v1/audio/speed",
        json={
            "file_path": staged_audio,
            "speed": 20.0,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_speed_missing_speed_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing required `speed` field → Pydantic 422."""
    r = client.post(
        "/v1/audio/speed",
        json={
            "file_path": staged_audio,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 422, r.text


def test_speed_missing_file_404(client: httpx.Client) -> None:
    """file_path pointing to a non-staged file → 404."""
    r = client.post(
        "/v1/audio/speed",
        json={
            "file_path": "no/such.wav",
            "speed": 2.0,
            "output_path": "out/missing.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_speed_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    r = client.post(
        "/v1/audio/speed",
        json={
            "file_path": staged_audio,
            "speed": 1.5,
            "output_path": "speed/fast.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "speed/fast.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)
