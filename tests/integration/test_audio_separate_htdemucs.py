"""End-to-end test for ``POST /v1/audio/separate`` with ``engine=htdemucs``.

Demucs Hybrid Transformer (htdemucs) — Meta's open-licence 4-stem
separator (vocals / drums / bass / other). CPU-capable (slow) but
realistically used on GPU. Engine slug is a JSON body field, NOT a path
segment — the route is ``/v1/audio/separate``.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav, assert_zip

pytestmark = [pytest.mark.engine("htdemucs")]


def test_separate_single_stem_returns_audio(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Single stem requested → response is raw audio bytes, not a ZIP."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "htdemucs",
            "stems": ["vocals"],
            "output_format": "wav",
            "output_path": "out/htdemucs_vocals.wav",
        },
        timeout=600.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/htdemucs_vocals.wav"
    assert body["engine"] == "htdemucs"
    assert body["stem"] == "vocals"
    assert body["output_format"] == "wav"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_separate_all_stems_returns_zip(
    client: httpx.Client, staged_audio: str,
) -> None:
    """All 4 stems requested → response carries a ZIP with one entry per
    stem."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "htdemucs",
            "stems": ["vocals", "drums", "bass", "other"],
            "output_format": "wav",
            "output_path": "out/htdemucs_all.zip",
        },
        timeout=600.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/htdemucs_all.zip"
    assert body["engine"] == "htdemucs"
    assert set(body.get("stems", [])) == {"vocals", "drums", "bass", "other"}

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_zip(fetched.content)


def test_separate_rejects_unknown_engine(
    client: httpx.Client, staged_audio: str,
) -> None:
    """An engine slug that's not registered → 404."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "this-does-not-exist",
            "stems": ["vocals"],
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_separate_rejects_unknown_stem(
    client: httpx.Client, staged_audio: str,
) -> None:
    """A stem name not in the engine's available set → 400."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "htdemucs",
            "stems": ["not-a-real-stem"],
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_separate_requires_input(client: httpx.Client) -> None:
    """Missing both file_path and file_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "engine": "htdemucs",
            "stems": ["vocals"],
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_separate_requires_output(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing both output_path and output_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/separate",
        json={
            "file_path": staged_audio,
            "engine": "htdemucs",
            "stems": ["vocals"],
        },
    )
    assert r.status_code == 400, r.text
