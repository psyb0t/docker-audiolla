"""End-to-end test for ``POST /v1/audio/separate`` with ``engine=mdx_extra``.

MDX-Net extra (MUSDB-trained) — 4-stem separator, particularly strong on
vocal isolation. Open weights, CPU-capable.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav, assert_zip

pytestmark = [
    pytest.mark.engine("mdx_extra"),
    # mdx_extra is registered in engines.json (CUDA image) but NOT in
    # engines-cpu.json — CPU image keeps only htdemucs to stay slim.
    # Mark as gpu so CPU runs skip cleanly.
    pytest.mark.gpu,
]

_STEMS_4 = ["drums", "bass", "other", "vocals"]


def test_separate_single_stem_returns_audio(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Single stem requested → response is raw audio bytes."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "mdx_extra",
            "stems": ["vocals"],
            "output_format": "wav",
            "output_path": "out/mdx_extra_vocals.wav",
        },
        timeout=600.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "mdx_extra"
    assert body["stem"] == "vocals"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_separate_all_stems_returns_zip(
    client: httpx.Client, staged_audio: str,
) -> None:
    """All 4 stems requested → ZIP."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "mdx_extra",
            "stems": _STEMS_4,
            "output_format": "wav",
            "output_path": "out/mdx_extra_all.zip",
        },
        timeout=600.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.get("stems", [])) == set(_STEMS_4)

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
            "engine": "mdx_extra",
            "stems": ["not-a-real-stem"],
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 400, r.text
