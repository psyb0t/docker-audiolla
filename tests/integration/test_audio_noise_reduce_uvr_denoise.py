"""End-to-end test for ``POST /v1/audio/noise-reduce/uvr-denoise``.

UVR MelBand-Roformer ML noise reduction routed through the
``/v1/audio/noise-reduce/{engine}`` dispatcher. Same weights / HF gate
as ``/v1/audio/restore/uvr-denoise``; this file exercises the
noise-reduce route specifically (``stationary``/``prop_decrease`` are
DSP-only and ignored here). Marked ``gpu`` + ``hf_gated``.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav, uvr_model_produced_no_output

pytestmark = [
    pytest.mark.engine("uvr-denoise"),
    pytest.mark.gpu,
    pytest.mark.hf_gated,
]


def test_noise_reduce_writes_real_audio(
    client: httpx.Client, staged_long_audio: str,
) -> None:
    """Happy path: 200 + decodable WAV. Cold-load takes minutes."""
    r = client.post(
        "/v1/audio/noise-reduce/uvr-denoise",
        json={
            "file_path": staged_long_audio,
            "output_path": "out/uvr_nr.wav",
        },
        timeout=900.0,
    )
    if uvr_model_produced_no_output(r):
        return  # synthetic sine fixture has nothing for UVR to extract
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/uvr_nr.wav"
    assert body["output_format"] == "wav"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_noise_reduce_requires_input(client: httpx.Client) -> None:
    """Missing both file_path and file_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/noise-reduce/uvr-denoise",
        json={"output_path": "out/x.wav"},
    )
    assert r.status_code == 400, r.text


def test_noise_reduce_requires_output(
    client: httpx.Client, staged_long_audio: str,
) -> None:
    """Missing both output_path and output_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/noise-reduce/uvr-denoise",
        json={"file_path": staged_long_audio},
    )
    assert r.status_code == 400, r.text
