"""End-to-end test for ``POST /v1/audio/eq``.

Parametric EQ via ffmpeg equalizer filter. `bands` is a JSON array of
{freq, gain_db, width_hz} objects.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_mp3, assert_wav

pytestmark = pytest.mark.engine("fx-chain")


ONE_BAND = [{"freq": 1000, "gain_db": 3.0, "width_hz": 100}]
TWO_BANDS = [
    {"freq": 200, "gain_db": -6.0, "width_hz": 50},
    {"freq": 8000, "gain_db": 6.0, "width_hz": 500},
]


def test_eq_returns_wav(client: httpx.Client, staged_audio: str) -> None:
    """Single-band EQ returns a valid WAV at the staged path."""
    r = client.post(
        "/v1/audio/eq",
        json={
            "file_path": staged_audio,
            "bands": ONE_BAND,
            "output_path": "out/eq_one.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_eq_multiple_bands(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Multiple bands stack → 200."""
    r = client.post(
        "/v1/audio/eq",
        json={
            "file_path": staged_audio,
            "bands": TWO_BANDS,
            "output_path": "out/eq_two.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_eq_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    r = client.post(
        "/v1/audio/eq",
        json={
            "file_path": staged_audio,
            "bands": ONE_BAND,
            "output_format": "mp3",
            "output_path": "out/eq.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_eq_invalid_bands_type_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """`bands` must be an array — passing a string → Pydantic 422."""
    r = client.post(
        "/v1/audio/eq",
        json={
            "file_path": staged_audio,
            "bands": "not-json",
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 422, r.text


def test_eq_missing_bands_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing required `bands` → Pydantic 422."""
    r = client.post(
        "/v1/audio/eq",
        json={
            "file_path": staged_audio,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 422, r.text


def test_eq_missing_file_404(client: httpx.Client) -> None:
    """file_path pointing to a non-staged file → 404."""
    r = client.post(
        "/v1/audio/eq",
        json={
            "file_path": "no/such.wav",
            "bands": ONE_BAND,
            "output_path": "out/missing.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_eq_output_path(client: httpx.Client, staged_audio: str) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    r = client.post(
        "/v1/audio/eq",
        json={
            "file_path": staged_audio,
            "bands": ONE_BAND,
            "output_path": "eq/out.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "eq/out.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)
