"""End-to-end tests for ``POST /v1/audio/vad``.

Silero voice activity detection. JSON-only response with speech_segments
array + speech_ratio. Configurable threshold and min durations.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.engine("silero-vad")


def test_vad_returns_speech_segments(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response has speech_segments (array) + speech_ratio (number)."""
    r = client.post("/v1/audio/vad", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["speech_segments"], list)
    assert isinstance(body["speech_ratio"], (int, float))


def test_vad_rejects_missing_file(client: httpx.Client) -> None:
    """No input → 4xx."""
    r = client.post("/v1/audio/vad")
    assert 400 <= r.status_code < 500, r.text


def test_vad_custom_threshold(
    client: httpx.Client, staged_audio: str,
) -> None:
    """threshold=0.7 is echoed back in the response."""
    r = client.post(
        "/v1/audio/vad",
        json={"file_path": staged_audio, "threshold": 0.7},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["speech_segments"], list)
    assert body["threshold"] == 0.7


def test_vad_min_speech_duration_ms(
    client: httpx.Client, staged_audio: str,
) -> None:
    """min_speech_duration_ms=500 → no segment shorter than 0.499s."""
    r = client.post(
        "/v1/audio/vad",
        json={"file_path": staged_audio, "min_speech_duration_ms": 500},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    segs = body["speech_segments"]
    assert isinstance(segs, list)
    short = [s for s in segs if (s["end_sec"] - s["start_sec"]) < 0.499]
    assert not short, f"{len(short)} segments shorter than 500ms: {short}"


def test_vad_min_silence_duration_ms(
    client: httpx.Client, staged_audio: str,
) -> None:
    """min_silence_duration_ms accepted, response shape preserved."""
    r = client.post(
        "/v1/audio/vad",
        json={"file_path": staged_audio, "min_silence_duration_ms": 500},
    )
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["speech_segments"], list)
