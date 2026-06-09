"""End-to-end tests for ``POST /v1/audio/silence``.

Silence detection + optional trim. Without trim_mode → JSON with
silent_ranges + non_silent_ranges. With trim_mode → trimmed audio
returned as base64, or staged at output_path.
"""

from __future__ import annotations

import base64
import io
import math
import secrets
import struct
import wave

import httpx
import pytest

from .helpers import assert_wav

pytestmark = pytest.mark.engine("silence-detect")


def _make_silence_padded_wav() -> bytes:
    """Construct a 7-second mono 44.1 kHz WAV with this structure:

        - 2 s of 440 Hz sine at 0.5 amplitude
        - 3 s of pure silence
        - 2 s of 880 Hz sine at 0.5 amplitude

    Returns the raw WAV bytes — used by the silence-detection tests to
    have a known gap to find. Replaces the bash fixture builder which
    shelled out to ffmpeg.
    """
    sr = 44100
    amp = 0.5
    samples: list[float] = []
    # 2s @ 440Hz
    samples.extend(amp * math.sin(2 * math.pi * 440 * t / sr) for t in range(sr * 2))
    # 3s silence
    samples.extend([0.0] * (sr * 3))
    # 2s @ 880Hz
    samples.extend(amp * math.sin(2 * math.pi * 880 * t / sr) for t in range(sr * 2))

    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(sr)
        frames = b"".join(
            struct.pack("<h", max(-32767, min(32767, int(s * 32767))))
            for s in samples
        )
        w.writeframes(frames)
    return buf.getvalue()


@pytest.fixture
def staged_silence_padded(client: httpx.Client) -> str:
    """PUT a synthetic sine-silence-sine WAV and return its staged path."""
    rel = f"uploads/silence-{secrets.token_hex(8)}.wav"
    r = client.put(
        f"/v1/files/{rel}",
        content=_make_silence_padded_wav(),
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code in (200, 201), r.text
    return rel


def test_silence_detect_finds_gap(
    client: httpx.Client, staged_silence_padded: str,
) -> None:
    """The 3 s pure-silence gap is detected with duration ~3 s."""
    r = client.post(
        "/v1/audio/silence",
        json={
            "file_path": staged_silence_padded,
            "threshold_db": -30,
            "min_duration_sec": 1.0,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["silent_ranges"], list)
    assert len(body["silent_ranges"]) >= 1, f"no silence detected: {body}"
    gap = body["silent_ranges"][0]
    assert 2.5 < gap["duration_sec"] < 3.5, (
        f"gap not ~3s: {gap['duration_sec']}"
    )
    assert isinstance(body["non_silent_ranges"], list)


def test_silence_trim_all_returns_shorter_audio(
    client: httpx.Client, staged_silence_padded: str,
) -> None:
    """trim_mode=all removes the gap; trimmed_audio_base64 decodes to a
    shorter WAV than the input."""
    r = client.post(
        "/v1/audio/silence",
        json={
            "file_path": staged_silence_padded,
            "threshold_db": -30,
            "min_duration_sec": 1.0,
            "trim_mode": "all",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    b64 = body.get("trimmed_audio_base64")
    assert b64, f"missing trimmed_audio_base64: {str(body)[:500]}"
    trimmed = base64.b64decode(b64)
    assert_wav(trimmed, min_bytes=100)

    # Input is 7 s; trimmed should be ~4 s. Compare against the original.
    input_bytes = _make_silence_padded_wav()
    assert len(trimmed) < len(input_bytes), (
        f"trimmed ({len(trimmed)}) not smaller than input ({len(input_bytes)})"
    )


def test_silence_trim_edges_output_path(
    client: httpx.Client, staged_silence_padded: str,
) -> None:
    """trim_mode=edges + output_path stages a real WAV at the named slot."""
    r = client.post(
        "/v1/audio/silence",
        json={
            "file_path": staged_silence_padded,
            "threshold_db": -30,
            "min_duration_sec": 1.0,
            "trim_mode": "edges",
            "output_path": "silence/trimmed.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "silence/trimmed.wav"

    fetched = client.get("/v1/files/silence/trimmed.wav")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_silence_bad_threshold_400(
    client: httpx.Client, staged_silence_padded: str,
) -> None:
    """Positive dBFS threshold (5) is rejected with 400/422 + 'threshold' in detail."""
    r = client.post(
        "/v1/audio/silence",
        json={
            "file_path": staged_silence_padded,
            "threshold_db": 5,
        },
    )
    assert r.status_code in (400, 422), r.text
    assert "threshold" in r.text.lower()
