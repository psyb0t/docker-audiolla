"""End-to-end test for ``POST /v1/audio/thumbnail``.

Extracts the most representative segment of a track (default 30s; clips
to track length on short files). librosa-analyze provides the structural
analysis used to pick the segment. CPU-only.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_audio_decodable, assert_mp3, assert_wav

pytestmark = pytest.mark.engine("librosa-analyze")


def test_thumbnail_short_file_returns_whole(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Default 30s thumbnail on an 8s fixture → entire file returned."""
    r = client.post(
        "/v1/audio/thumbnail",
        json={
            "file_path": staged_audio,
            "output_path": "out/thumb.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/thumb.wav"
    assert body["size"] > 100_000

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100_000)


def test_thumbnail_4s_from_8s_file(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``duration_sec=4`` on the 8s fixture → output duration ~4s
    (allow 3.5-5.0s window for boundary rounding)."""
    r = client.post(
        "/v1/audio/thumbnail",
        json={
            "file_path": staged_audio,
            "duration_sec": 4,
            "output_path": "out/thumb_4s.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    info = client.post("/v1/audio/info", json={"file_path": body["path"]})
    assert info.status_code == 200, info.text
    dur = info.json()["duration_sec"]
    assert 3.5 <= dur <= 5.0, f"thumbnail duration {dur:.2f}s outside [3.5, 5.0]"


def test_thumbnail_output_path_metadata(
    client: httpx.Client, staged_audio: str,
) -> None:
    """JSON response includes ``start_sec`` and ``end_sec`` segment markers."""
    r = client.post(
        "/v1/audio/thumbnail",
        json={
            "file_path": staged_audio,
            "duration_sec": 4,
            "output_path": "thumb_test/segment.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "thumb_test/segment.wav"
    assert "start_sec" in body and "end_sec" in body
    assert body["start_sec"] >= 0
    assert body["end_sec"] > body["start_sec"]

    fetched = client.get("/v1/files/thumb_test/segment.wav")
    assert fetched.status_code == 200
    assert_wav(fetched.content)


def test_thumbnail_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_format=mp3`` stages an MP3."""
    r = client.post(
        "/v1/audio/thumbnail",
        json={
            "file_path": staged_audio,
            "duration_sec": 4,
            "output_format": "mp3",
            "output_path": "out/thumb.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_thumbnail_invalid_duration(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``duration_sec=0`` rejected."""
    r = client.post(
        "/v1/audio/thumbnail",
        json={
            "file_path": staged_audio,
            "duration_sec": 0,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_thumbnail_decodable(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Output is decodable regardless of the format selected (cross-check
    helper)."""
    r = client.post(
        "/v1/audio/thumbnail",
        json={
            "file_path": staged_audio,
            "duration_sec": 4,
            "output_path": "out/thumb_decode.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert_audio_decodable(fetched.content, min_duration_sec=3.0)
