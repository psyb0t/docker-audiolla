"""End-to-end test for ``POST /v1/audio/generate/stable-audio-open``.

Stability Stable Audio Open 1.0 (stabilityai/stable-audio-open-1.0) —
Stability Community Licence (commercial use under revenue cap); the
weights are HF-licence-gated so a token with the licence accepted must
be present. 44.1 kHz stereo. Cap: 47 s. Loops / SFX / textures — no
vocals.

CUDA-only — the engine refuses to load on CPU. Test is marked
``@pytest.mark.gpu`` and ``@pytest.mark.hf_gated`` so CPU-only / no-token
runs auto-skip.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav

pytestmark = [
    pytest.mark.engine("stable-audio-open"),
    pytest.mark.gpu,
    pytest.mark.hf_gated,
]


def test_generate_writes_real_audio(client: httpx.Client) -> None:
    """Happy path: generate ~3 s of texture at 50 inference steps (the
    default 100 is slow; 50 is the documented quality/speed tradeoff).
    Confirm the staged WAV is decodable, ≥ 2 s, and stereo @ 44.1 kHz."""
    r = client.post(
        "/v1/audio/generate/stable-audio-open",
        json={
            "prompt": "warm analog pad with slow attack",
            "duration_sec": 3.0,
            "num_inference_steps": 50,
            "seed": 42,
            "output_path": "gen/sao_test.wav",
        },
        timeout=600.0,  # cold model load can take minutes
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "gen/sao_test.wav"
    assert body["size"] > 10_000
    assert body["engine"] == "stable-audio-open"
    assert body["output_format"] == "wav"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    # 44.1 kHz stereo at 3 s ≈ 530 kB raw. min_bytes 50 kB is a safe floor.
    # min_duration 2.0 s leaves slack for the model occasionally producing
    # slightly shorter clips than requested.
    assert_wav(
        fetched.content,
        min_bytes=50_000,
        min_duration_sec=2.0,
        expected_samplerate=44100,
    )


def test_generate_requires_prompt(client: httpx.Client) -> None:
    """Missing ``prompt`` field → 422 (Pydantic missing-field error)."""
    r = client.post(
        "/v1/audio/generate/stable-audio-open",
        json={"output_path": "gen/x.wav"},
    )
    assert r.status_code == 422


def test_generate_requires_output(client: httpx.Client) -> None:
    """Missing both output_path and output_url → 400 (output xor validator)."""
    r = client.post(
        "/v1/audio/generate/stable-audio-open",
        json={"prompt": "test", "duration_sec": 2.0},
    )
    assert r.status_code == 400, r.text


def test_generate_rejects_excessive_duration(client: httpx.Client) -> None:
    """stable-audio-open's per-engine duration cap is 47 s. Asking for
    more → 400 from the engine validator."""
    r = client.post(
        "/v1/audio/generate/stable-audio-open",
        json={
            "prompt": "test",
            "duration_sec": 999.0,
            "output_path": "gen/x.wav",
        },
    )
    assert r.status_code == 400, r.text
