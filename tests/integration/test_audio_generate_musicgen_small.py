"""End-to-end test for ``POST /v1/audio/generate/musicgen-small``.

Meta MusicGen 300M (facebook/musicgen-small) — CC-BY-NC weights. Requires
``AUDIOLLA_ENABLE_NONCOMMERCIAL=1`` to opt in to the non-commercial
licence, plus an HF token with the gated repo accepted. 32 kHz mono, cap
30 s, instrumental only (``lyrics`` is accepted for API uniformity but
ignored).

CUDA-only. Marked ``gpu`` + ``hf_gated`` + ``noncommercial`` so any
missing prerequisite auto-skips with a clear reason.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav

pytestmark = [
    pytest.mark.engine("musicgen-small"),
    pytest.mark.gpu,
    pytest.mark.hf_gated,
    pytest.mark.noncommercial,
]


def test_generate_writes_real_audio(client: httpx.Client) -> None:
    """Happy path: generate 3 s of music with a fixed seed. Confirm the
    staged WAV is decodable, ≥ 2 s, and 32 kHz mono (MusicGen's native
    sample rate)."""
    r = client.post(
        "/v1/audio/generate/musicgen-small",
        json={
            "prompt": "upbeat acoustic guitar riff in C major",
            "duration_sec": 3.0,
            "seed": 42,
            "output_path": "gen/musicgen_small_test.wav",
        },
        timeout=600.0,  # cold model load can take minutes
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "gen/musicgen_small_test.wav"
    assert body["size"] > 10_000
    assert body["engine"] == "musicgen-small"
    assert body["output_format"] == "wav"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(
        fetched.content,
        min_bytes=20_000,
        min_duration_sec=2.0,
        expected_channels=1,
        expected_samplerate=32000,
    )


def test_generate_requires_prompt(client: httpx.Client) -> None:
    """Missing ``prompt`` field → 422 (Pydantic missing-field error)."""
    r = client.post(
        "/v1/audio/generate/musicgen-small",
        json={"output_path": "gen/x.wav"},
    )
    assert r.status_code == 422


def test_generate_requires_output(client: httpx.Client) -> None:
    """Missing both output_path and output_url → 400 (output xor validator)."""
    r = client.post(
        "/v1/audio/generate/musicgen-small",
        json={"prompt": "test", "duration_sec": 2.0},
    )
    assert r.status_code == 400, r.text


def test_generate_rejects_excessive_duration(client: httpx.Client) -> None:
    """musicgen-small's per-engine duration cap is 30 s. Asking for
    more → 400 from the engine validator."""
    r = client.post(
        "/v1/audio/generate/musicgen-small",
        json={
            "prompt": "test",
            "duration_sec": 999.0,
            "output_path": "gen/x.wav",
        },
    )
    assert r.status_code == 400, r.text
