"""End-to-end test for ``POST /v1/audio/conv-reverb``.

Convolution reverb using an impulse response (IR) file. wet_mix ∈
[0.0, 1.0]: 0=dry, 1=wet.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav

pytestmark = pytest.mark.engine("fx-chain")


def test_conv_reverb_returns_wav(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """Primary + IR (use the staged_reference as IR) → valid WAV."""
    r = client.post(
        "/v1/audio/conv-reverb",
        json={
            "file_path": staged_audio,
            "ir_file_path": staged_reference,
            "wet_mix": 0.3,
            "output_path": "out/conv_reverb.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100_000)


def test_conv_reverb_dry_only(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """wet_mix=0.0 → dry-only: output exists and decodes as WAV."""
    r = client.post(
        "/v1/audio/conv-reverb",
        json={
            "file_path": staged_audio,
            "ir_file_path": staged_reference,
            "wet_mix": 0.0,
            "output_path": "out/conv_reverb_dry.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_conv_reverb_invalid_wet_mix_400(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """wet_mix=1.5 outside [0.0, 1.0] → 400 (or 422)."""
    r = client.post(
        "/v1/audio/conv-reverb",
        json={
            "file_path": staged_audio,
            "ir_file_path": staged_reference,
            "wet_mix": 1.5,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_conv_reverb_output_path(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    r = client.post(
        "/v1/audio/conv-reverb",
        json={
            "file_path": staged_audio,
            "ir_file_path": staged_reference,
            "wet_mix": 0.4,
            "output_path": "conv_reverb_test/reverbed.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "conv_reverb_test/reverbed.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)
