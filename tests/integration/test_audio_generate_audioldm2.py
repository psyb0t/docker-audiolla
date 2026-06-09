"""End-to-end test for ``POST /v1/audio/generate/audioldm2``.

AudioLDM 2 (cvssp/audioldm2) — CC-BY 4.0 weights (commercial-safe, no
opt-in gate, ungated on HuggingFace). General-purpose text-to-SFX:
ambience, foley, mechanical sounds, impacts. 16 kHz mono, up to 30 s,
~8-10 GB VRAM at fp16 with CPU offload.

CUDA-only — non-CUDA hosts get HTTP 400 at engine load. Marked
``@pytest.mark.gpu`` so a CPU-only ``pytest`` run skips this with a
clear reason.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav

pytestmark = [
    pytest.mark.engine("audioldm2"),
    pytest.mark.gpu,
    # No hf_gated / noncommercial markers — audioldm2 is open licence
    # AND ungated on HuggingFace, so anonymous downloads work.
]


def test_generate_writes_real_audio(client: httpx.Client) -> None:
    """Happy path: generate 4 seconds of ambient noise at 50 inference
    steps (the default 200-step DDIM is slow; 50 is the documented
    quality/speed tradeoff). Verify the staged WAV is decodable and at
    least as long as we asked for."""
    r = client.post(
        "/v1/audio/generate/audioldm2",
        json={
            "prompt": "soft ambient drone with subtle reverb",
            "duration_sec": 4.0,
            "num_inference_steps": 50,
            "seed": 42,
            "output_path": "gen/audioldm2_test.wav",
        },
        timeout=600.0,  # cold load + 4s inference at 50 steps
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "gen/audioldm2_test.wav"
    assert body["size"] > 10_000
    assert body["engine"] == "audioldm2"
    assert body["output_format"] == "wav"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    # audioldm2 emits 16 kHz mono by default; min_duration 3s is a
    # safety margin under the 4s request — accounts for the model
    # occasionally returning a slightly shorter clip than asked.
    assert_wav(
        fetched.content,
        min_bytes=50_000,
        min_duration_sec=3.0,
        expected_channels=1,
    )


def test_generate_requires_prompt(client: httpx.Client) -> None:
    """Missing ``prompt`` field → 422 (Pydantic missing-field error)."""
    r = client.post(
        "/v1/audio/generate/audioldm2",
        json={"output_path": "gen/x.wav"},
    )
    assert r.status_code == 422


def test_generate_requires_output(client: httpx.Client) -> None:
    """Missing both output_path and output_url → 400 (output xor validator)."""
    r = client.post(
        "/v1/audio/generate/audioldm2",
        json={"prompt": "test", "duration_sec": 2.0},
    )
    assert r.status_code == 400, r.text


def test_generate_rejects_excessive_duration(client: httpx.Client) -> None:
    """audioldm2's per-engine duration cap is 30 s. Asking for more →
    400 from the engine validator."""
    r = client.post(
        "/v1/audio/generate/audioldm2",
        json={
            "prompt": "test",
            "duration_sec": 999.0,
            "output_path": "gen/x.wav",
        },
    )
    assert r.status_code == 400, r.text
