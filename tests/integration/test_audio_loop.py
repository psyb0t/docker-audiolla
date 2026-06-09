"""End-to-end test for ``POST /v1/audio/loop``.

Repeat audio count times (minimum 2). Uses ffmpeg aloop filter.
"""

from __future__ import annotations

import httpx

from .helpers import assert_mp3, assert_wav


def test_loop_returns_wav(client: httpx.Client, staged_audio: str) -> None:
    """count=2 returns a valid WAV at the staged path."""
    r = client.post(
        "/v1/audio/loop",
        json={
            "file_path": staged_audio,
            "count": 2,
            "output_path": "out/loop2.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_loop_output_longer(
    client: httpx.Client, staged_audio: str,
) -> None:
    """count=2 output is at least ~1.5x the source duration."""
    src = client.post("/v1/audio/info", json={"file_path": staged_audio})
    src_dur = float(src.json()["duration_sec"])

    r = client.post(
        "/v1/audio/loop",
        json={
            "file_path": staged_audio,
            "count": 2,
            "output_path": "out/loop_dur.wav",
        },
    )
    assert r.status_code == 200, r.text

    info = client.post(
        "/v1/audio/info", json={"file_path": "out/loop_dur.wav"},
    )
    loop_dur = float(info.json()["duration_sec"])
    assert loop_dur > src_dur * 1.5


def test_loop_count_3(client: httpx.Client, staged_audio: str) -> None:
    """count=3 succeeds."""
    r = client.post(
        "/v1/audio/loop",
        json={
            "file_path": staged_audio,
            "count": 3,
            "output_path": "out/loop3.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_loop_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    r = client.post(
        "/v1/audio/loop",
        json={
            "file_path": staged_audio,
            "count": 2,
            "output_format": "mp3",
            "output_path": "out/loop.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_loop_count_1_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """count=1 violates count>=2 → 400 (or 422)."""
    r = client.post(
        "/v1/audio/loop",
        json={
            "file_path": staged_audio,
            "count": 1,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_loop_missing_file_404(client: httpx.Client) -> None:
    """file_path pointing to a non-staged file → 404."""
    r = client.post(
        "/v1/audio/loop",
        json={
            "file_path": "no/such.wav",
            "count": 2,
            "output_path": "out/missing.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_loop_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    r = client.post(
        "/v1/audio/loop",
        json={
            "file_path": staged_audio,
            "count": 2,
            "output_path": "loop/out.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "loop/out.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)
