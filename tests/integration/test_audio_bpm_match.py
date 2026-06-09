"""End-to-end test for ``POST /v1/audio/bpm-match``.

Detects source BPM via librosa-analyze then time-stretches to ``target_bpm``
using the stretch engine. Pure DSP, CPU-only — runs in seconds.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_mp3, assert_wav

pytestmark = pytest.mark.engine("librosa-analyze", "stretch")


def test_bpm_match_returns_wav(
    client: httpx.Client, staged_beat: str,
) -> None:
    """Happy path: stretch the 120 BPM click track to 120 BPM. Output is a
    decodable WAV staged at ``output_path``."""
    r = client.post(
        "/v1/audio/bpm-match",
        json={
            "file_path": staged_beat,
            "target_bpm": 120.0,
            "output_path": "out/bpm.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/bpm.wav"
    assert body["size"] > 100

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_bpm_match_json_metadata(
    client: httpx.Client, staged_beat: str,
) -> None:
    """Response carries ``source_bpm`` and ``target_bpm`` so callers can
    record the detected source tempo."""
    r = client.post(
        "/v1/audio/bpm-match",
        json={
            "file_path": staged_beat,
            "target_bpm": 140.0,
            "output_path": "bpm/matched.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "source_bpm" in body
    assert body["target_bpm"] == 140.0


def test_bpm_match_with_pitch(
    client: httpx.Client, staged_beat: str,
) -> None:
    """``pitch_semitones`` parameter is accepted and audio is still produced."""
    r = client.post(
        "/v1/audio/bpm-match",
        json={
            "file_path": staged_beat,
            "target_bpm": 100.0,
            "pitch_semitones": 2.0,
            "output_path": "out/bpm_pitched.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_bpm_match_output_format_mp3(
    client: httpx.Client, staged_beat: str,
) -> None:
    """``output_format=mp3`` stages an MP3 instead of WAV."""
    r = client.post(
        "/v1/audio/bpm-match",
        json={
            "file_path": staged_beat,
            "target_bpm": 120.0,
            "output_format": "mp3",
            "output_path": "out/bpm.mp3",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/bpm.mp3"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_bpm_match_zero_target_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``target_bpm <= 0`` rejected by handler-level guard."""
    r = client.post(
        "/v1/audio/bpm-match",
        json={
            "file_path": staged_audio,
            "target_bpm": 0,
            "output_path": "out/zero.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_bpm_match_missing_target_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing required ``target_bpm`` → 422 from Pydantic."""
    r = client.post(
        "/v1/audio/bpm-match",
        json={
            "file_path": staged_audio,
            "output_path": "out/nope.wav",
        },
    )
    assert r.status_code == 422, r.text


def test_bpm_match_missing_file(client: httpx.Client) -> None:
    """Reference to a file that doesn't exist → 400/404/422."""
    r = client.post(
        "/v1/audio/bpm-match",
        json={
            "file_path": "no/such.wav",
            "target_bpm": 120.0,
            "output_path": "out/ghost.wav",
        },
    )
    assert r.status_code in (400, 404, 422), r.text
