"""End-to-end tests for ``POST /v1/audio/clip-detect``.

Digital clipping detection. JSON-only response with clipped, clip_count,
clip_ratio, peak_db, duration_sec, sample_rate, channels.
"""

from __future__ import annotations

import httpx


def test_clip_detect_clean_audio(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Clean sine fixture → response carries clipped + peak_db, ~8s @ 44.1 kHz."""
    r = client.post("/v1/audio/clip-detect", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "clipped" in body
    assert isinstance(body["peak_db"], (int, float))
    assert 7.0 < body["duration_sec"] < 9.0
    assert body["sample_rate"] == 44100


def test_clip_detect_response_shape(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries every documented field."""
    r = client.post("/v1/audio/clip-detect", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    for field in (
        "clipped",
        "clip_count",
        "clip_ratio",
        "peak_db",
        "duration_sec",
        "sample_rate",
        "channels",
    ):
        assert field in body, f"missing field {field!r}: {body}"


def test_clip_detect_via_file_path_after_convert(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Convert → restage → clip-detect on the staged copy still returns shape."""
    conv = client.post(
        "/v1/audio/convert",
        json={"file_path": staged_audio, "output_path": "clip_test/input.wav"},
    )
    assert conv.status_code == 200, conv.text
    assert conv.json()["path"] == "clip_test/input.wav"

    r = client.post(
        "/v1/audio/clip-detect",
        json={"file_path": "clip_test/input.wav"},
    )
    assert r.status_code == 200, r.text
    assert "clipped" in r.json()
