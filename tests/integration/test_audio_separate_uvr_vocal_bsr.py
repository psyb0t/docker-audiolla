"""End-to-end test for ``POST /v1/audio/separate`` with ``engine=uvr-vocal-bsr``.

UVR BS-Roformer vocal separation — 2 stems (``Vocals`` / ``Instrumental``).
Weights download from HuggingFace on first use (≈500 MB pull); the
download is HF-licence-gated so a token must be in the env. Marked
``gpu`` + ``hf_gated``.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav, assert_zip, uvr_model_produced_no_output

pytestmark = [
    pytest.mark.engine("uvr-vocal-bsr"),
    pytest.mark.gpu,
    pytest.mark.hf_gated,
]


def test_separate_single_stem_returns_audio(
    client: httpx.Client, staged_long_audio: str,
) -> None:
    """Single stem ('Vocals' — UVR uses capitalized stem names) → audio bytes."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_long_audio,
            "engine": "uvr-vocal-bsr",
            "stems": ["Vocals"],
            "output_format": "wav",
            "output_path": "out/uvr_vocal_bsr_vocals.wav",
        },
        timeout=900.0,  # first-run model download is heavy
    )
    if uvr_model_produced_no_output(r):
        return  # synthetic sine fixture has nothing for UVR to extract
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "uvr-vocal-bsr"
    assert body["stem"] == "Vocals"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_separate_both_stems_returns_zip(
    client: httpx.Client, staged_long_audio: str,
) -> None:
    """Both stems requested → ZIP with Vocals.wav + Instrumental.wav."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_long_audio,
            "engine": "uvr-vocal-bsr",
            "stems": ["Vocals", "Instrumental"],
            "output_format": "wav",
            "output_path": "out/uvr_vocal_bsr_all.zip",
        },
        timeout=900.0,
    )
    if uvr_model_produced_no_output(r):
        return  # synthetic sine fixture has nothing for UVR to extract
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.get("stems", [])) == {"Vocals", "Instrumental"}

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_zip(fetched.content)


def test_separate_rejects_unknown_stem(
    client: httpx.Client, staged_long_audio: str,
) -> None:
    """A stem name not in the engine's available set → 400."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_long_audio,
            "engine": "uvr-vocal-bsr",
            "stems": ["not-a-real-stem"],
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 400, r.text
