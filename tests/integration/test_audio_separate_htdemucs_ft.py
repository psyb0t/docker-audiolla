"""End-to-end test for ``POST /v1/audio/separate`` with ``engine=htdemucs_ft``.

Demucs Hybrid Transformer fine-tuned (htdemucs_ft) — 4 sub-models, ~320
MB of weights, marked ``cuda_only=true`` in engines.json. On CPU hosts
the engine refuses to load and the route returns 422.

Marked ``@pytest.mark.gpu`` — CPU-only pytest runs auto-skip.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav, assert_zip

pytestmark = [
    pytest.mark.engine("htdemucs_ft"),
    pytest.mark.gpu,
]


def test_separate_single_stem_returns_audio(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Single stem on CUDA → 200 with audio bytes."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "htdemucs_ft",
            "stems": ["vocals"],
            "output_format": "wav",
            "output_path": "out/htdemucs_ft_vocals.wav",
        },
        timeout=900.0,  # 4 sub-models, slow on first cold load
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "htdemucs_ft"
    assert body["stem"] == "vocals"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_separate_all_stems_returns_zip(
    client: httpx.Client, staged_audio: str,
) -> None:
    """All 4 stems requested → ZIP response."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "htdemucs_ft",
            "stems": ["vocals", "drums", "bass", "other"],
            "output_format": "wav",
            "output_path": "out/htdemucs_ft_all.zip",
        },
        timeout=900.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body.get("stems", [])) == {"vocals", "drums", "bass", "other"}

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
            "engine": "htdemucs_ft",
            "stems": ["not-a-real-stem"],
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 400, r.text
