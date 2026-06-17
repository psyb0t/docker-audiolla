"""End-to-end test for ``POST /v1/audio/trim``.

Cut audio to [start_sec, end_sec). end_sec is required.
"""

from __future__ import annotations

import httpx

from .helpers import assert_mp3, assert_wav


def test_trim_returns_wav(client: httpx.Client, staged_audio: str) -> None:
    """Happy path: returns 200 with a staged WAV."""
    r = client.post(
        "/v1/audio/trim",
        json={
            "file_path": staged_audio,
            "start_sec": 1.0,
            "end_sec": 4.0,
            "output_path": "out/trim.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_trim_output_is_shorter(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Trimming 0..3 seconds yields a file shorter than the 8s source."""
    src = client.post(
        "/v1/audio/info", json={"file_path": staged_audio},
    )
    assert src.status_code == 200
    src_dur = float(src.json()["duration_sec"])

    r = client.post(
        "/v1/audio/trim",
        json={
            "file_path": staged_audio,
            "start_sec": 0.0,
            "end_sec": 3.0,
            "output_path": "out/trim_short.wav",
        },
    )
    assert r.status_code == 200, r.text

    info = client.post(
        "/v1/audio/info", json={"file_path": "out/trim_short.wav"},
    )
    trim_dur = float(info.json()["duration_sec"])
    assert trim_dur < src_dur
    assert trim_dur <= 3.5  # 0.5 s slop


def test_trim_default_start_sec(
    client: httpx.Client, staged_audio: str,
) -> None:
    """start_sec defaults to 0; only end_sec required → 200."""
    r = client.post(
        "/v1/audio/trim",
        json={
            "file_path": staged_audio,
            "end_sec": 2.0,
            "output_path": "out/trim_default.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_trim_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    r = client.post(
        "/v1/audio/trim",
        json={
            "file_path": staged_audio,
            "start_sec": 0.0,
            "end_sec": 2.0,
            "output_format": "mp3",
            "output_path": "out/trim.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_trim_omitted_end_sec_defaults_to_source_end(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Omitting end_sec trims from start_sec to the source duration.

    The synthetic fixture is 8 s; trimming start_sec=3.0 without end_sec
    should produce ~5 s of audio (handler probes ffprobe for duration).
    """
    r = client.post(
        "/v1/audio/trim",
        json={
            "file_path": staged_audio,
            "start_sec": 3.0,
            "output_path": "out/trim_to_end.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # end_sec echoed back in the response — should be ~8.0 (source dur).
    assert body.get("end_sec", 0.0) >= 7.5, body
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_duration_sec=4.5)


def test_trim_end_before_start_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """end_sec <= start_sec → 400 or 422."""
    r = client.post(
        "/v1/audio/trim",
        json={
            "file_path": staged_audio,
            "start_sec": 5.0,
            "end_sec": 2.0,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_trim_negative_start_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Negative start_sec → 400 or 422."""
    r = client.post(
        "/v1/audio/trim",
        json={
            "file_path": staged_audio,
            "start_sec": -1.0,
            "end_sec": 3.0,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_trim_missing_file_404(client: httpx.Client) -> None:
    """file_path pointing to a non-staged file → 404."""
    r = client.post(
        "/v1/audio/trim",
        json={
            "file_path": "no/such.wav",
            "end_sec": 3.0,
            "output_path": "out/missing.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_trim_output_path(client: httpx.Client, staged_audio: str) -> None:
    """Response contains `path`; the staged file is retrievable as WAV."""
    r = client.post(
        "/v1/audio/trim",
        json={
            "file_path": staged_audio,
            "start_sec": 0.0,
            "end_sec": 2.0,
            "output_path": "trim/out.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "trim/out.wav"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)
