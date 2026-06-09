"""End-to-end test for ``POST /v1/audio/pan``.

Pan audio in the stereo field. position: -1.0=hard left, 0.0=center,
1.0=hard right.
"""

from __future__ import annotations

import httpx

from .helpers import assert_mp3, assert_wav


def test_pan_center(client: httpx.Client, staged_audio: str) -> None:
    """Default position (center) returns a valid WAV."""
    r = client.post(
        "/v1/audio/pan",
        json={
            "file_path": staged_audio,
            "output_path": "out/pan_center.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_pan_hard_left(client: httpx.Client, staged_audio: str) -> None:
    """position=-1.0 (hard left) is accepted → 200."""
    r = client.post(
        "/v1/audio/pan",
        json={
            "file_path": staged_audio,
            "position": -1.0,
            "output_path": "out/pan_left.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_pan_hard_right(client: httpx.Client, staged_audio: str) -> None:
    """position=1.0 (hard right) is accepted → 200."""
    r = client.post(
        "/v1/audio/pan",
        json={
            "file_path": staged_audio,
            "position": 1.0,
            "output_path": "out/pan_right.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_pan_output_stereo(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Output is stereo (channels=2) regardless of input layout."""
    r = client.post(
        "/v1/audio/pan",
        json={
            "file_path": staged_audio,
            "position": 0.5,
            "output_path": "out/pan_stereo.wav",
        },
    )
    assert r.status_code == 200, r.text

    info = client.post(
        "/v1/audio/info", json={"file_path": "out/pan_stereo.wav"},
    )
    assert info.json()["channels"] == 2


def test_pan_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    r = client.post(
        "/v1/audio/pan",
        json={
            "file_path": staged_audio,
            "position": 0.0,
            "output_format": "mp3",
            "output_path": "out/pan.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_pan_out_of_range_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """position=2.0 outside [-1.0, 1.0] → 400 (or 422)."""
    r = client.post(
        "/v1/audio/pan",
        json={
            "file_path": staged_audio,
            "position": 2.0,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_pan_missing_file_404(client: httpx.Client) -> None:
    """file_path pointing to a non-staged file → 404."""
    r = client.post(
        "/v1/audio/pan",
        json={
            "file_path": "no/such.wav",
            "output_path": "out/missing.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_pan_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    r = client.post(
        "/v1/audio/pan",
        json={
            "file_path": staged_audio,
            "position": -0.5,
            "output_path": "pan/left.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "pan/left.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)
