"""End-to-end test for ``POST /v1/audio/split``.

Splits audio into segments by either equal length (``mode=equal``,
requires ``count>=2``) or detected silence boundaries
(``mode=silence``, uses the silence-detect engine). Returns a ZIP of
numbered segments.
"""

from __future__ import annotations

import io
import zipfile

import httpx
import pytest

from .helpers import assert_zip

pytestmark = pytest.mark.engine("silence-detect")


def test_split_equal_returns_zip(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``mode=equal`` with ``count=2`` → 200 with a valid ZIP body."""
    r = client.post(
        "/v1/audio/split",
        json={
            "file_path": staged_audio,
            "mode": "equal",
            "count": 2,
            "output_path": "split/eq2.zip",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "split/eq2.zip"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_zip(fetched.content)


def test_split_equal_segment_count(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``count=3`` yields exactly 3 entries inside the ZIP."""
    r = client.post(
        "/v1/audio/split",
        json={
            "file_path": staged_audio,
            "mode": "equal",
            "count": 3,
            "output_path": "split/eq3.zip",
        },
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{r.json()['path']}")
    with zipfile.ZipFile(io.BytesIO(fetched.content)) as z:
        assert len(z.namelist()) == 3


def test_split_equal_count_4(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``count=4`` → 200 (smoke test for upper count values)."""
    r = client.post(
        "/v1/audio/split",
        json={
            "file_path": staged_audio,
            "mode": "equal",
            "count": 4,
            "output_path": "split/eq4.zip",
        },
    )
    assert r.status_code == 200, r.text


def test_split_silence_returns_zip(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``mode=silence`` with a generous ``threshold_db`` → 200 with at
    least one non-silent segment."""
    r = client.post(
        "/v1/audio/split",
        json={
            "file_path": staged_audio,
            "mode": "silence",
            "threshold_db": -20.0,
            "output_path": "split/silence.zip",
        },
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{r.json()['path']}")
    with zipfile.ZipFile(io.BytesIO(fetched.content)) as z:
        assert len(z.namelist()) >= 1


def test_split_equal_missing_count_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``mode=equal`` without ``count`` → 400 from handler guard."""
    r = client.post(
        "/v1/audio/split",
        json={
            "file_path": staged_audio,
            "mode": "equal",
            "output_path": "split/bad.zip",
        },
    )
    assert r.status_code == 400, r.text


def test_split_invalid_mode_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Unknown ``mode`` → 422 from Pydantic enum validator."""
    r = client.post(
        "/v1/audio/split",
        json={
            "file_path": staged_audio,
            "mode": "random",
            "output_path": "split/bad.zip",
        },
    )
    assert r.status_code == 422, r.text


def test_split_missing_file_404(client: httpx.Client) -> None:
    """Reference to a missing file → 404."""
    r = client.post(
        "/v1/audio/split",
        json={
            "file_path": "no/such.wav",
            "mode": "equal",
            "count": 2,
            "output_path": "split/miss.zip",
        },
    )
    assert r.status_code == 404, r.text


def test_split_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_path`` is honoured and the staged file is a valid ZIP
    with at least one entry."""
    r = client.post(
        "/v1/audio/split",
        json={
            "file_path": staged_audio,
            "mode": "equal",
            "count": 2,
            "output_path": "split/out.zip",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == "split/out.zip"

    fetched = client.get("/v1/files/split/out.zip")
    assert fetched.status_code == 200
    with zipfile.ZipFile(io.BytesIO(fetched.content)) as z:
        assert len(z.namelist()) > 0
