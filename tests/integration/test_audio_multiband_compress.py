"""End-to-end test for ``POST /v1/audio/multiband-compress``.

N-band compressor. crossovers_hz: ascending crossover frequencies;
bands: per-band compressor specs (len = len(crossovers_hz)+1).
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_mp3, assert_wav

pytestmark = pytest.mark.engine("fx-chain")


THREE_BANDS_CROSSOVERS = [200, 2000]
THREE_BANDS_SPEC = [
    {"threshold_db": -18, "ratio": 4, "attack_ms": 10, "release_ms": 100, "makeup_db": 1.0},
    {"threshold_db": -12, "ratio": 3, "attack_ms": 8, "release_ms": 80, "makeup_db": 0.5},
    {"threshold_db": -6, "ratio": 2, "attack_ms": 4, "release_ms": 40, "makeup_db": 0.0},
]

ONE_CROSSOVER = [1000]
TWO_BANDS_SPEC = [
    {"threshold_db": -18, "ratio": 4},
    {"threshold_db": -12, "ratio": 3},
]

FOUR_BANDS_CROSSOVERS = [150, 800, 4000]
FOUR_BANDS_SPEC = [
    {"threshold_db": -20, "ratio": 5, "attack_ms": 20, "release_ms": 200, "makeup_db": 2.0},
    {"threshold_db": -16, "ratio": 4, "attack_ms": 12, "release_ms": 120, "makeup_db": 1.5},
    {"threshold_db": -12, "ratio": 3, "attack_ms": 6, "release_ms": 60, "makeup_db": 1.0},
    {"threshold_db": -8, "ratio": 2, "attack_ms": 2, "release_ms": 30, "makeup_db": 0.5},
]


def test_multiband_3band_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """3-band split returns a valid WAV at the staged path."""
    r = client.post(
        "/v1/audio/multiband-compress",
        json={
            "file_path": staged_audio,
            "crossovers_hz": THREE_BANDS_CROSSOVERS,
            "bands": THREE_BANDS_SPEC,
            "output_path": "mbc-out/r3.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_multiband_4band_full_params(
    client: httpx.Client, staged_audio: str,
) -> None:
    """4-band split with full per-band params → 200."""
    r = client.post(
        "/v1/audio/multiband-compress",
        json={
            "file_path": staged_audio,
            "crossovers_hz": FOUR_BANDS_CROSSOVERS,
            "bands": FOUR_BANDS_SPEC,
            "output_path": "mbc-out/r4.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_multiband_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response includes path + crossovers_hz; staged file fetchable as WAV."""
    r = client.post(
        "/v1/audio/multiband-compress",
        json={
            "file_path": staged_audio,
            "crossovers_hz": ONE_CROSSOVER,
            "bands": TWO_BANDS_SPEC,
            "output_path": "mbc_test/out.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "mbc_test/out.wav"
    assert len(body["crossovers_hz"]) == 1

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_multiband_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    r = client.post(
        "/v1/audio/multiband-compress",
        json={
            "file_path": staged_audio,
            "crossovers_hz": ONE_CROSSOVER,
            "bands": TWO_BANDS_SPEC,
            "output_format": "mp3",
            "output_path": "mbc-out/out.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_multiband_bad_bands_length_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """len(bands) != len(crossovers_hz) + 1 → handler-level 400."""
    r = client.post(
        "/v1/audio/multiband-compress",
        json={
            "file_path": staged_audio,
            "crossovers_hz": THREE_BANDS_CROSSOVERS,
            "bands": [{"threshold_db": -18, "ratio": 4}],
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_multiband_empty_crossovers_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Empty crossovers_hz → handler-level 400."""
    r = client.post(
        "/v1/audio/multiband-compress",
        json={
            "file_path": staged_audio,
            "crossovers_hz": [],
            "bands": [{"threshold_db": -18, "ratio": 4}],
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_multiband_missing_fields_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing required fields (crossovers_hz, bands) → Pydantic 422."""
    r = client.post(
        "/v1/audio/multiband-compress",
        json={
            "file_path": staged_audio,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 422, r.text


def test_multiband_crossover_above_nyquist_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """A crossover frequency >= Nyquist (>22.05 kHz at 44.1 kHz) → 400."""
    r = client.post(
        "/v1/audio/multiband-compress",
        json={
            "file_path": staged_audio,
            "crossovers_hz": [40000],
            "bands": [
                {"threshold_db": -18, "ratio": 4},
                {"threshold_db": -12, "ratio": 3},
            ],
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 400, r.text
