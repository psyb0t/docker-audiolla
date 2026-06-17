"""End-to-end tests for ``POST /v1/audio/info``.

Audio metadata probe — duration, sample rate, channels, codec, format,
size. JSON-only response, no engine declaration needed.
"""

from __future__ import annotations

from pathlib import Path

import httpx

_FIXTURES_DIR = Path(__file__).resolve().parent / ".fixtures"


def test_info_returns_required_fields(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries every documented field."""
    r = client.post("/v1/audio/info", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    for field in (
        "duration_sec",
        "sample_rate",
        "channels",
        "codec",
        "format",
        "size_bytes",
    ):
        assert field in body, f"missing field {field!r}: {body}"


def test_info_duration_is_positive(
    client: httpx.Client, staged_audio: str,
) -> None:
    """duration_sec > 0."""
    r = client.post("/v1/audio/info", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    assert r.json()["duration_sec"] > 0


def test_info_sample_rate_44100(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Fixture is 44.1 kHz."""
    r = client.post("/v1/audio/info", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    assert r.json()["sample_rate"] == 44100


def test_info_channels_stereo(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Fixture is stereo (2 channels)."""
    r = client.post("/v1/audio/info", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    assert r.json()["channels"] == 2


def test_info_size_bytes_matches_file(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Reported size_bytes equals the on-disk fixture size."""
    actual = (_FIXTURES_DIR / "audio.wav").stat().st_size
    r = client.post("/v1/audio/info", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    assert r.json()["size_bytes"] == actual


def test_info_missing_file_404(client: httpx.Client) -> None:
    """Nonexistent file_path → 404."""
    r = client.post("/v1/audio/info", json={"file_path": "no/such.wav"})
    assert r.status_code == 404, r.text


def test_info_no_input_422(client: httpx.Client) -> None:
    """No body at all → 422."""
    r = client.post("/v1/audio/info")
    assert r.status_code == 422, r.text


def test_info_on_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Regression: ffprobe -v quiet swallowed real error messages, leaving
    callers with "ffprobe failed: unknown error" on any failure. Also,
    `info` must succeed on MP3 inputs — historical bug had it returning
    that unhelpful error on valid MP3 files."""
    # Convert the staged WAV to MP3 first, then info-probe the MP3.
    conv = client.post(
        "/v1/audio/convert",
        json={
            "file_path": staged_audio,
            "output_format": "mp3",
            "output_path": "out/probe.mp3",
        },
    )
    assert conv.status_code == 200, conv.text
    mp3_path = conv.json()["path"]

    r = client.post("/v1/audio/info", json={"file_path": mp3_path})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["codec"] == "mp3", body
    assert body["duration_sec"] > 0, body
    assert body["channels"] >= 1, body
