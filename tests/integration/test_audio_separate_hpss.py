"""End-to-end test for ``POST /v1/audio/separate/hpss``.

Harmonic/percussive source separation via librosa HPSS median filter.
Returns a ZIP archive containing ``harmonic.<fmt>`` and ``percussive.<fmt>``.
CPU-only DSP.
"""

from __future__ import annotations

import io
import zipfile

import httpx
import pytest

from .helpers import assert_wav, assert_zip

pytestmark = pytest.mark.engine("hpss")


def test_hpss_returns_zip(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Happy path: response is JSON, the staged blob is a ZIP archive."""
    r = client.post(
        "/v1/audio/separate/hpss",
        json={
            "file_path": staged_audio,
            "output_path": "hpss-out/result.zip",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "hpss-out/result.zip"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_zip(fetched.content)


def test_hpss_zip_contains_both_stems(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Both ``harmonic.wav`` and ``percussive.wav`` appear in the archive."""
    r = client.post(
        "/v1/audio/separate/hpss",
        json={
            "file_path": staged_audio,
            "output_path": "hpss-out/stems.zip",
        },
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    with zipfile.ZipFile(io.BytesIO(fetched.content)) as z:
        names = z.namelist()
    assert "harmonic.wav" in names, names
    assert "percussive.wav" in names, names


def test_hpss_stems_are_valid_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Each stem inside the archive is a decodable WAV."""
    r = client.post(
        "/v1/audio/separate/hpss",
        json={
            "file_path": staged_audio,
            "output_path": "hpss-out/valid.zip",
        },
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{r.json()['path']}")
    with zipfile.ZipFile(io.BytesIO(fetched.content)) as z:
        for stem in ("harmonic.wav", "percussive.wav"):
            assert_wav(z.read(stem))


def test_hpss_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_format=mp3`` switches both stem extensions to .mp3."""
    r = client.post(
        "/v1/audio/separate/hpss",
        json={
            "file_path": staged_audio,
            "output_format": "mp3",
            "output_path": "hpss-out/mp3.zip",
        },
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{r.json()['path']}")
    with zipfile.ZipFile(io.BytesIO(fetched.content)) as z:
        names = z.namelist()
    assert "harmonic.mp3" in names, names
    assert "percussive.mp3" in names, names


def test_hpss_missing_file_404(client: httpx.Client) -> None:
    """Reference to a missing file → 404 from file resolver."""
    r = client.post(
        "/v1/audio/separate/hpss",
        json={
            "file_path": "nonexistent/ghost.wav",
            "output_path": "hpss-out/ghost.zip",
        },
    )
    assert r.status_code == 404, r.text


def test_hpss_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_path`` is honoured and the staged file is a ZIP."""
    r = client.post(
        "/v1/audio/separate/hpss",
        json={
            "file_path": staged_audio,
            "output_path": "hpss/stems.zip",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == "hpss/stems.zip"

    fetched = client.get("/v1/files/hpss/stems.zip")
    assert fetched.status_code == 200
    assert_zip(fetched.content)
