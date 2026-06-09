"""End-to-end test for ``POST /v1/audio/noise-reduce/noise-reduce``.

DSP (spectral-gating) noise reduction via the ``noisereduce`` library —
``stationary`` toggles stationary vs non-stationary mode; ``prop_decrease``
in [0.0, 1.0] dials the aggressiveness. CPU-fine, no GPU needed.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_mp3, assert_wav

pytestmark = [pytest.mark.engine("noise-reduce")]


def test_noise_reduce_writes_real_audio(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Default (non-stationary) mode → 200 + decodable WAV."""
    r = client.post(
        "/v1/audio/noise-reduce/noise-reduce",
        json={
            "file_path": staged_audio,
            "output_path": "out/nr.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/nr.wav"
    assert body["output_format"] == "wav"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_noise_reduce_stationary_mode(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``stationary=true`` (constant hum/hiss) → 200 + WAV."""
    r = client.post(
        "/v1/audio/noise-reduce/noise-reduce",
        json={
            "file_path": staged_audio,
            "stationary": True,
            "output_path": "out/nr_stat.wav",
        },
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_noise_reduce_partial_decrease(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``prop_decrease=0.5`` → 200, partial reduction still produces audio."""
    r = client.post(
        "/v1/audio/noise-reduce/noise-reduce",
        json={
            "file_path": staged_audio,
            "prop_decrease": 0.5,
            "output_path": "out/nr_half.wav",
        },
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert_wav(fetched.content, min_bytes=10_000)


def test_noise_reduce_invalid_prop_decrease(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``prop_decrease`` outside [0.0, 1.0] → 400 with ``prop_decrease`` in
    the detail (or 422 if Pydantic catches it first)."""
    r = client.post(
        "/v1/audio/noise-reduce/noise-reduce",
        json={
            "file_path": staged_audio,
            "prop_decrease": 1.5,
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code in (400, 422), r.text
    if r.status_code == 400:
        assert "prop_decrease" in r.text


def test_noise_reduce_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_format=mp3`` → response carries an MP3."""
    r = client.post(
        "/v1/audio/noise-reduce/noise-reduce",
        json={
            "file_path": staged_audio,
            "output_format": "mp3",
            "output_path": "out/nr.mp3",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["output_format"] == "mp3"
    assert body["size"] > 1000

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_noise_reduce_missing_file(client: httpx.Client) -> None:
    """A file_path that doesn't exist in the staging dir → 400/404/422."""
    r = client.post(
        "/v1/audio/noise-reduce/noise-reduce",
        json={
            "file_path": "nonexistent/phantom.wav",
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code in (400, 404, 422), r.text


def test_noise_reduce_requires_input(client: httpx.Client) -> None:
    """Missing both file_path and file_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/noise-reduce/noise-reduce",
        json={"output_path": "out/x.wav"},
    )
    assert r.status_code == 400, r.text


def test_noise_reduce_requires_output(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing both output_path and output_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/noise-reduce/noise-reduce",
        json={"file_path": staged_audio},
    )
    assert r.status_code == 400, r.text
