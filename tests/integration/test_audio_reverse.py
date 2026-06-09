"""End-to-end test for ``POST /v1/audio/reverse``.

Reverse audio playback direction via ffmpeg areverse.
"""

from __future__ import annotations

import httpx

from .helpers import assert_mp3, assert_wav


def test_reverse_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Happy path: reverse returns a valid WAV."""
    r = client.post(
        "/v1/audio/reverse",
        json={
            "file_path": staged_audio,
            "output_path": "out/reverse.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_reverse_preserves_duration(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Duration is preserved within 0.5 s rounding tolerance."""
    src = client.post("/v1/audio/info", json={"file_path": staged_audio})
    assert src.status_code == 200
    src_dur = float(src.json()["duration_sec"])

    r = client.post(
        "/v1/audio/reverse",
        json={
            "file_path": staged_audio,
            "output_path": "out/reverse_dur.wav",
        },
    )
    assert r.status_code == 200, r.text

    info = client.post(
        "/v1/audio/info", json={"file_path": "out/reverse_dur.wav"},
    )
    assert abs(src_dur - float(info.json()["duration_sec"])) <= 0.5


def test_reverse_double_roundtrip(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Reversing twice yields a valid WAV (the original orientation)."""
    r1 = client.post(
        "/v1/audio/reverse",
        json={
            "file_path": staged_audio,
            "output_path": "out/reverse_once.wav",
        },
    )
    assert r1.status_code == 200, r1.text

    r2 = client.post(
        "/v1/audio/reverse",
        json={
            "file_path": "out/reverse_once.wav",
            "output_path": "out/reverse_twice.wav",
        },
    )
    assert r2.status_code == 200, r2.text
    fetched = client.get(f"/v1/files/{r2.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_reverse_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    r = client.post(
        "/v1/audio/reverse",
        json={
            "file_path": staged_audio,
            "output_format": "mp3",
            "output_path": "out/reverse.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_reverse_missing_file_404(client: httpx.Client) -> None:
    """file_path pointing to a non-staged file → 404."""
    r = client.post(
        "/v1/audio/reverse",
        json={
            "file_path": "no/such.wav",
            "output_path": "out/missing.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_reverse_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    r = client.post(
        "/v1/audio/reverse",
        json={
            "file_path": staged_audio,
            "output_path": "reverse/out.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "reverse/out.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)
