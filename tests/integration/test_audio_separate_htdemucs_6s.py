"""End-to-end test for ``POST /v1/audio/separate`` with ``engine=htdemucs_6s``.

Demucs Hybrid Transformer 6-stem variant — same backbone as ``htdemucs``
but extended to ``drums / bass / other / vocals / guitar / piano``. CPU-
capable (slow); production runs use GPU.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav, assert_zip

pytestmark = [
    pytest.mark.engine("htdemucs_6s"),
    # htdemucs_6s is registered in engines.json (CUDA image) but NOT in
    # engines-cpu.json — CPU image keeps only htdemucs to stay slim.
    # Mark as gpu so CPU runs skip cleanly.
    pytest.mark.gpu,
]

_STEMS_6 = ["drums", "bass", "other", "vocals", "guitar", "piano"]


def test_separate_single_stem_returns_audio(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Single stem ('guitar' — exclusive to the 6-stem variant) → audio bytes."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "htdemucs_6s",
            "stems": ["guitar"],
            "output_format": "wav",
            "output_path": "out/htdemucs_6s_guitar.wav",
        },
        timeout=600.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "htdemucs_6s"
    assert body["stem"] == "guitar"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_separate_all_stems_returns_zip(
    client: httpx.Client, staged_audio: str,
) -> None:
    """All 6 stems requested → ZIP response with one entry per stem."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "htdemucs_6s",
            "stems": _STEMS_6,
            "output_format": "wav",
            "output_path": "out/htdemucs_6s_all.zip",
        },
        timeout=600.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.get("stems", [])) == set(_STEMS_6)

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_zip(fetched.content)


def test_separate_rejects_unknown_stem(
    client: httpx.Client, staged_audio: str,
) -> None:
    """A stem name not in the engine's available set → 400."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "htdemucs_6s",
            "stems": ["not-a-real-stem"],
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 400, r.text
