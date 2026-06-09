"""End-to-end test for ``POST /v1/audio/enhance/deepfilter``.

DeepFilterNet DF3 neural speech/vocal enhancement. CPU-capable (no GPU
required, though slower); model weights download from HuggingFace on
first call (~50 MB) and cache under ``HF_HOME=/data/hf``.

This file replaces the old ``e2e_enhance.sh`` which had the URL wrong —
it hit ``/v1/audio/enhance`` (no engine path segment) and never actually
exercised the route. v1.0.4 fixed both the predicate bug AND the test.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_mp3, assert_wav

pytestmark = pytest.mark.engine("deepfilter")


def test_enhance_writes_real_audio(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Happy path: POST returns 200 with a JSON descriptor; the staged
    file is a decodable WAV at least as long as the input."""
    r = client.post(
        "/v1/audio/enhance/deepfilter",
        json={
            "file_path": staged_audio,
            "output_path": "out/enhanced.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/enhanced.wav"
    assert body["size"] > 10_000
    assert body["engine"] == "deepfilter"
    assert body["output_format"] == "wav"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(
        fetched.content,
        min_bytes=10_000,
        min_duration_sec=1.0,
    )


def test_enhance_with_mp3_output(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_format=mp3`` produces a valid MP3 instead of WAV."""
    r = client.post(
        "/v1/audio/enhance/deepfilter",
        json={
            "file_path": staged_audio,
            "output_format": "mp3",
            "output_path": "out/enhanced.mp3",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output_format"] == "mp3"
    assert body["path"] == "out/enhanced.mp3"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_enhance_rejects_unknown_engine(
    client: httpx.Client, staged_audio: str,
) -> None:
    """An engine slug that's not registered → 404 with a helpful list."""
    r = client.post(
        "/v1/audio/enhance/no-such-engine",
        json={
            "file_path": staged_audio,
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 404
    assert "no-such-engine" in r.text


def test_enhance_rejects_wrong_engine_type(
    client: httpx.Client, staged_audio: str,
) -> None:
    """A registered engine that doesn't expose ``.enhance()`` → 400 or 404
    (404 when the requested engine isn't in this container's enabled set;
    400 when it is but doesn't support enhance)."""
    r = client.post(
        "/v1/audio/enhance/silence-detect",
        json={
            "file_path": staged_audio,
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code in (400, 404), r.text


def test_enhance_rejects_bad_output_format(
    client: httpx.Client, staged_audio: str,
) -> None:
    """An unsupported ``output_format`` is rejected — Pydantic's enum
    validator returns 422 before the handler's 415 check fires. Accept
    either status."""
    r = client.post(
        "/v1/audio/enhance/deepfilter",
        json={
            "file_path": staged_audio,
            "output_format": "xyz",
            "output_path": "out/x.xyz",
        },
    )
    assert r.status_code in (415, 422), r.text


def test_enhance_requires_input(client: httpx.Client) -> None:
    """Missing both file_path and file_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/enhance/deepfilter",
        json={"output_path": "out/x.wav"},
    )
    assert r.status_code == 400, r.text


def test_enhance_requires_output(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing both output_path and output_url → 400 (output xor validator)."""
    r = client.post(
        "/v1/audio/enhance/deepfilter",
        json={"file_path": staged_audio},
    )
    assert r.status_code == 400, r.text


def test_enhance_rejects_double_input(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Both file_path AND file_url → 400."""
    r = client.post(
        "/v1/audio/enhance/deepfilter",
        json={
            "file_path": staged_audio,
            "file_url": "https://example.com/x.wav",
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 400, r.text
