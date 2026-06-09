"""End-to-end test for ``POST /v1/audio/deess``.

Split-band de-esser: compress sibilance above frequency_hz. Ranges:
ratio ∈ [1.0, 50.0], frequency_hz ∈ [1000, 16000].
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_mp3, assert_wav

pytestmark = pytest.mark.engine("fx-chain")


def test_deess_default_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Default params produce a valid WAV."""
    r = client.post(
        "/v1/audio/deess",
        json={
            "file_path": staged_audio,
            "output_path": "out/deess.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_deess_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Custom threshold_db and frequency_hz echo into the response."""
    r = client.post(
        "/v1/audio/deess",
        json={
            "file_path": staged_audio,
            "threshold_db": -15,
            "frequency_hz": 7000,
            "output_path": "deess_test/out.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "deess_test/out.wav"
    assert body["threshold_db"] == -15

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_deess_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    r = client.post(
        "/v1/audio/deess",
        json={
            "file_path": staged_audio,
            "output_format": "mp3",
            "output_path": "out/deess.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_deess_invalid_ratio_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """ratio=100 outside [1, 50] → 400 (or 422)."""
    r = client.post(
        "/v1/audio/deess",
        json={
            "file_path": staged_audio,
            "ratio": 100,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_deess_invalid_frequency_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """frequency_hz=100 outside [1000, 16000] → 400 (or 422)."""
    r = client.post(
        "/v1/audio/deess",
        json={
            "file_path": staged_audio,
            "frequency_hz": 100,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text
