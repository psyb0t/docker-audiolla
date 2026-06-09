"""End-to-end test for ``POST /v1/audio/stereo-width``.

M/S-based stereo width adjustment. ``width=0`` collapses to mono,
``1.0`` passes through, ``>1.0`` widens. Always emits stereo. Pure DSP,
no engine required (M/S processing happens in the handler).
"""

from __future__ import annotations

import httpx

from .helpers import assert_mp3, assert_wav


def test_stereo_width_default(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Happy path: default width (1.0) passes audio through unchanged."""
    r = client.post(
        "/v1/audio/stereo-width",
        json={
            "file_path": staged_audio,
            "output_path": "out/sw.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/sw.wav"
    assert body["size"] > 100

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_stereo_width_mono_collapse(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``width=0.0`` mono-collapses but still emits a stereo file
    (the M/S filter always outputs 2 channels via ``aformat=stereo``)."""
    r = client.post(
        "/v1/audio/stereo-width",
        json={
            "file_path": staged_audio,
            "width": 0.0,
            "output_path": "out/sw_mono.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    info = client.post("/v1/audio/info", json={"file_path": body["path"]})
    assert info.status_code == 200, info.text
    assert info.json()["channels"] == 2


def test_stereo_width_wide(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``width=2.0`` widens; should return 200."""
    r = client.post(
        "/v1/audio/stereo-width",
        json={
            "file_path": staged_audio,
            "width": 2.0,
            "output_path": "out/sw_wide.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_stereo_width_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_format=mp3`` stages an MP3 instead of WAV."""
    r = client.post(
        "/v1/audio/stereo-width",
        json={
            "file_path": staged_audio,
            "width": 1.0,
            "output_format": "mp3",
            "output_path": "out/sw.mp3",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_stereo_width_out_of_range(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``width > 3.0`` rejected by handler-level range check."""
    r = client.post(
        "/v1/audio/stereo-width",
        json={
            "file_path": staged_audio,
            "width": 5.0,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_stereo_width_negative(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``width < 0.0`` rejected by handler-level range check."""
    r = client.post(
        "/v1/audio/stereo-width",
        json={
            "file_path": staged_audio,
            "width": -0.5,
            "output_path": "out/neg.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_stereo_width_missing_file_404(client: httpx.Client) -> None:
    """Reference to a missing file → 404."""
    r = client.post(
        "/v1/audio/stereo-width",
        json={
            "file_path": "no/such.wav",
            "output_path": "out/ghost.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_stereo_width_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_path`` is honoured and the staged WAV has a proper RIFF header."""
    r = client.post(
        "/v1/audio/stereo-width",
        json={
            "file_path": staged_audio,
            "width": 1.5,
            "output_path": "stereo/wide.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "stereo/wide.wav"

    fetched = client.get("/v1/files/stereo/wide.wav")
    assert fetched.status_code == 200
    assert_wav(fetched.content)
