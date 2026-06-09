"""End-to-end test for ``POST /v1/audio/generate/riffusion``.

Riffusion v1 (riffusion/riffusion-model-v1) — CreativeML OpenRAIL-M
licence (open, commercial use OK, no HF licence gate). Stable-Diffusion
spectrogram → Griffin-Lim audio reconstruction. Lo-fi character, ~5 s
per pass at 22.05 kHz mono. Engine-level cap is 30 s but practical
output length is bounded by the spectrogram canvas size.

CUDA-only — diffusion pipeline needs GPU. Marked ``gpu``. No
``hf_gated`` (open repo) and no ``noncommercial`` (RAIL-M is permissive).
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav

pytestmark = [
    pytest.mark.engine("riffusion"),
    pytest.mark.gpu,
]


def test_generate_writes_real_audio(client: httpx.Client) -> None:
    """Happy path: generate ~4 s of lo-fi audio with a fixed seed. Confirm
    the staged WAV is decodable, ≥ 1 s, and 22.05 kHz mono (Riffusion's
    Griffin-Lim output format)."""
    r = client.post(
        "/v1/audio/generate/riffusion",
        json={
            "prompt": "lo-fi hip hop beat with vinyl crackle",
            "duration_sec": 4.0,
            "seed": 42,
            "output_path": "gen/riffusion_test.wav",
        },
        timeout=300.0,  # SD pipeline + Griffin-Lim
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "gen/riffusion_test.wav"
    assert body["size"] > 10_000
    assert body["engine"] == "riffusion"
    assert body["output_format"] == "wav"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    # Riffusion's canvas size dictates actual length — clip may be a bit
    # shorter than requested. min_duration 1.0 s is the safety floor.
    assert_wav(
        fetched.content,
        min_bytes=20_000,
        min_duration_sec=1.0,
        expected_channels=1,
        expected_samplerate=22050,
    )


def test_generate_requires_prompt(client: httpx.Client) -> None:
    """Missing ``prompt`` field → 422 (Pydantic missing-field error)."""
    r = client.post(
        "/v1/audio/generate/riffusion",
        json={"output_path": "gen/x.wav"},
    )
    assert r.status_code == 422


def test_generate_requires_output(client: httpx.Client) -> None:
    """Missing both output_path and output_url → 400 (output xor validator)."""
    r = client.post(
        "/v1/audio/generate/riffusion",
        json={"prompt": "test", "duration_sec": 2.0},
    )
    assert r.status_code == 400, r.text


def test_generate_rejects_excessive_duration(client: httpx.Client) -> None:
    """riffusion's per-engine duration cap is 30 s. Asking for more →
    400 from the engine validator."""
    r = client.post(
        "/v1/audio/generate/riffusion",
        json={
            "prompt": "test",
            "duration_sec": 999.0,
            "output_path": "gen/x.wav",
        },
    )
    assert r.status_code == 400, r.text
