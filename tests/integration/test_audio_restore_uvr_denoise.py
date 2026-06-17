"""End-to-end test for ``POST /v1/audio/restore/uvr-denoise``.

UVR MelBand-Roformer noise removal. Weights download from HuggingFace on
first use (licence-gated). Marked ``gpu`` + ``hf_gated``.

Note: ``uvr-denoise`` is also reachable via ``POST /v1/audio/noise-reduce/
uvr-denoise`` — that's covered by
``test_audio_noise_reduce_uvr_denoise.py``. This file specifically
exercises the ``restore/{engine}`` dispatch surface.
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


def test_restore_writes_real_audio(
    client: httpx.Client, staged_reverby: str,
) -> None:
    """Happy path on a heavily-reverb-y input. UVR's MelBand Roformer
    denoise splits the signal into "(noise)" and "(other)" stems;
    audiolla returns the clean stem as real WAV (≥ 10 s)."""
    r = client.post(
        "/v1/audio/restore/uvr-denoise",
        json={
            "file_path": staged_reverby,
            "output_path": "out/denoise.wav",
        },
        timeout=900.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/denoise.wav"
    assert body["engine"] == "uvr-denoise"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100_000, min_duration_sec=10.0)


def test_restore_requires_input(client: httpx.Client) -> None:
    """Missing both file_path and file_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/restore/uvr-denoise",
        json={"output_path": "out/x.wav"},
    )
    assert r.status_code == 400, r.text


def test_restore_requires_output(
    client: httpx.Client, staged_long_audio: str,
) -> None:
    """Missing both output_path and output_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/restore/uvr-denoise",
        json={"file_path": staged_long_audio},
    )
    assert r.status_code == 400, r.text
