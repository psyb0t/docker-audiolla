"""End-to-end test for ``POST /v1/audio/beat-slice``.

Slices audio at detected beat boundaries (via librosa-analyze) and
returns a ZIP archive containing one file per slice. CPU-only DSP.
"""

from __future__ import annotations

import io
import zipfile

import httpx
import pytest

from .helpers import assert_zip

pytestmark = pytest.mark.engine("librosa-analyze")


def test_beat_slice_returns_zip_of_wavs(
    client: httpx.Client, staged_beat: str,
) -> None:
    """Happy path: ZIP has ≥2 entries and every entry is a WAV (RIFF)."""
    r = client.post(
        "/v1/audio/beat-slice",
        json={
            "file_path": staged_beat,
            "output_path": "out/slices.zip",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/slices.zip"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_zip(fetched.content)

    with zipfile.ZipFile(io.BytesIO(fetched.content)) as z:
        names = z.namelist()
        assert len(names) >= 2, f"ZIP has only {len(names)} entries"
        for name in names:
            assert z.read(name).startswith(b"RIFF"), (
                f"ZIP entry {name!r} is not a WAV"
            )


def test_beat_slice_output_path(
    client: httpx.Client, staged_beat: str,
) -> None:
    """JSON response includes ``beat_count`` and the ZIP staged at
    ``output_path`` is fetchable + populated."""
    r = client.post(
        "/v1/audio/beat-slice",
        json={
            "file_path": staged_beat,
            "output_path": "beat_slice_test/slices.zip",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "beat_slice_test/slices.zip"
    assert isinstance(body.get("beat_count"), (int, float))

    fetched = client.get("/v1/files/beat_slice_test/slices.zip")
    assert fetched.status_code == 200
    with zipfile.ZipFile(io.BytesIO(fetched.content)) as z:
        assert len(z.namelist()) >= 2


def test_beat_slice_output_format_mp3(
    client: httpx.Client, staged_beat: str,
) -> None:
    """``output_format=mp3`` → every ZIP entry is an MP3 (ID3 prefix or
    MPEG sync)."""
    r = client.post(
        "/v1/audio/beat-slice",
        json={
            "file_path": staged_beat,
            "output_format": "mp3",
            "output_path": "out/slices_mp3.zip",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    with zipfile.ZipFile(io.BytesIO(fetched.content)) as z:
        for name in z.namelist():
            data = z.read(name)
            assert data[:3] == b"ID3" or (
                len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0
            ), f"ZIP entry {name!r} is not MP3"
