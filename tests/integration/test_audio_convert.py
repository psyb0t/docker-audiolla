"""End-to-end test for ``POST /v1/audio/convert``.

Re-encode audio to a different format, sample rate, or channel count.
Pure ffmpeg — no engine required.
"""

from __future__ import annotations

import httpx

from .helpers import assert_mp3, assert_wav


def test_convert_wav_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """WAV → WAV passthrough; staged output is a valid RIFF/WAVE."""
    r = client.post(
        "/v1/audio/convert",
        json={
            "file_path": staged_audio,
            "output_format": "wav",
            "output_path": "out/convert.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/convert.wav"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_convert_wav_to_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """WAV → MP3 produces a valid MP3 at the staged path."""
    r = client.post(
        "/v1/audio/convert",
        json={
            "file_path": staged_audio,
            "output_format": "mp3",
            "output_path": "out/convert.mp3",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/convert.mp3"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_convert_wav_to_flac(
    client: httpx.Client, staged_audio: str,
) -> None:
    """WAV → FLAC succeeds and the staged file is non-empty."""
    r = client.post(
        "/v1/audio/convert",
        json={
            "file_path": staged_audio,
            "output_format": "flac",
            "output_path": "out/convert.flac",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/convert.flac"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    # fLaC magic
    assert fetched.content[:4] == b"fLaC", (
        f"not a FLAC file (got {fetched.content[:4]!r})"
    )


def test_convert_sample_rate(
    client: httpx.Client, staged_audio: str,
) -> None:
    """sample_rate=22050 is honored; verify via /v1/audio/info on the output."""
    r = client.post(
        "/v1/audio/convert",
        json={
            "file_path": staged_audio,
            "output_format": "wav",
            "sample_rate": 22050,
            "output_path": "out/convert_22k.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["sample_rate"] == 22050

    info = client.post(
        "/v1/audio/info", json={"file_path": "out/convert_22k.wav"},
    )
    assert info.status_code == 200
    assert info.json()["sample_rate"] == 22050


def test_convert_to_mono(
    client: httpx.Client, staged_audio: str,
) -> None:
    """channels=1 produces a mono output; confirmed via /v1/audio/info."""
    r = client.post(
        "/v1/audio/convert",
        json={
            "file_path": staged_audio,
            "output_format": "wav",
            "channels": 1,
            "output_path": "out/convert_mono.wav",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["channels"] == 1

    info = client.post(
        "/v1/audio/info", json={"file_path": "out/convert_mono.wav"},
    )
    assert info.status_code == 200
    assert info.json()["channels"] == 1


def test_convert_invalid_channels_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """channels must be 1 or 2 — 3 → 400."""
    r = client.post(
        "/v1/audio/convert",
        json={
            "file_path": staged_audio,
            "channels": 3,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_convert_invalid_sample_rate_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """sample_rate must be > 0 — 0 → 400."""
    r = client.post(
        "/v1/audio/convert",
        json={
            "file_path": staged_audio,
            "sample_rate": 0,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_convert_missing_file_404(client: httpx.Client) -> None:
    """file_path pointing to a non-staged file → 404."""
    r = client.post(
        "/v1/audio/convert",
        json={
            "file_path": "no/such.wav",
            "output_path": "out/missing.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_convert_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Output is fetched back from /v1/files with non-zero size."""
    r = client.post(
        "/v1/audio/convert",
        json={
            "file_path": staged_audio,
            "output_format": "mp3",
            "output_path": "convert/out.mp3",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "convert/out.mp3"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)
