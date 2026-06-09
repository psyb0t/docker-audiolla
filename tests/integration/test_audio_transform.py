"""End-to-end test for ``POST /v1/audio/transform``.

pysox transform chain — gain, EQ, compand, reverb, pitch, tempo,
channels, trim, pad. CPU-only.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav

pytestmark = pytest.mark.engine("sox-transform")


def test_transform_gain(client: httpx.Client, staged_audio: str) -> None:
    """Single op: -3 dB gain returns a valid RIFF/WAVE."""
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "operations": [{"op": "gain", "params": {"db": -3}}],
            "output_format": "wav",
            "output_path": "out/tx_gain.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_transform_chain(client: httpx.Client, staged_audio: str) -> None:
    """4-op chain (EQ + compressor + reverb + gain) returns a sizable WAV."""
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "operations": [
                {"op": "equalizer", "params": {"frequency": 3000, "width_q": 1.5, "gain_db": 2}},
                {"op": "compand", "params": {
                    "attack_time": 0.02, "decay_time": 0.2, "soft_knee_db": 6,
                    "tf_points": [[-70, -70], [-30, -30], [-20, -15], [0, -10]],
                }},
                {"op": "reverb", "params": {"reverberance": 30, "pre_delay_ms": 0, "room_scale": 50}},
                {"op": "gain", "params": {"db": -1}},
            ],
            "output_format": "wav",
            "output_path": "out/tx_chain.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100_000)


def test_transform_pitch(client: httpx.Client, staged_audio: str) -> None:
    """Pitch shift +2 semitones returns a valid RIFF/WAVE."""
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "operations": [{"op": "pitch", "params": {"n_semitones": 2}}],
            "output_format": "wav",
            "output_path": "out/tx_pitch.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_transform_empty_ops(client: httpx.Client, staged_audio: str) -> None:
    """Empty operations list is the identity transform — still 200."""
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "operations": [],
            "output_format": "wav",
            "output_path": "out/tx_empty.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_transform_unknown_op_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Unknown op slug → handler-level 400 (not Pydantic 422)."""
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "operations": [{"op": "nope_unknown", "params": {}}],
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_transform_missing_operations_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing required `operations` field → Pydantic 422."""
    r = client.post(
        "/v1/audio/transform",
        json={
            "file_path": staged_audio,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 422, r.text
