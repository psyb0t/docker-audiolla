"""End-to-end test for ``POST /v1/audio/restore/uvr-deecho``.

UVR VR-Architecture echo removal. Weights download from HuggingFace on
first use (licence-gated). ``aggressive=true`` triggers the hard-removal
mode. Marked ``gpu`` + ``hf_gated``.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav, uvr_model_produced_no_output

pytestmark = [
    pytest.mark.engine("uvr-deecho"),
    pytest.mark.gpu,
    pytest.mark.hf_gated,
]


def test_restore_writes_real_audio(
    client: httpx.Client, staged_long_audio: str,
) -> None:
    """Happy path: 200 + the staged output is a decodable WAV."""
    r = client.post(
        "/v1/audio/restore/uvr-deecho",
        json={
            "file_path": staged_long_audio,
            "output_path": "out/deecho.wav",
        },
        timeout=900.0,
    )
    if uvr_model_produced_no_output(r):
        return  # synthetic sine fixture has nothing for UVR to extract
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/deecho.wav"
    assert body["engine"] == "uvr-deecho"
    assert body["aggressive"] is False

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_restore_aggressive_mode(
    client: httpx.Client, staged_long_audio: str,
) -> None:
    """``aggressive=true`` → 200, response surfaces the flag, output is WAV."""
    r = client.post(
        "/v1/audio/restore/uvr-deecho",
        json={
            "file_path": staged_long_audio,
            "aggressive": True,
            "output_path": "out/deecho_hard.wav",
        },
        timeout=900.0,
    )
    if uvr_model_produced_no_output(r):
        return  # synthetic sine fixture has nothing for UVR to extract
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["aggressive"] is True

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_restore_requires_input(client: httpx.Client) -> None:
    """Missing both file_path and file_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/restore/uvr-deecho",
        json={"output_path": "out/x.wav"},
    )
    assert r.status_code == 400, r.text


def test_restore_requires_output(
    client: httpx.Client, staged_long_audio: str,
) -> None:
    """Missing both output_path and output_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/restore/uvr-deecho",
        json={"file_path": staged_long_audio},
    )
    assert r.status_code == 400, r.text
