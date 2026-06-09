"""End-to-end test for ``POST /v1/audio/key-match``.

Detect musical key via the chord-detect engine, then pitch-shift via the
stretch engine to reach ``target_key``. Pure DSP, CPU-only.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_mp3, assert_wav

pytestmark = pytest.mark.engine("chord-detect", "stretch")


def test_key_match_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Happy path: key-match to C, response is a JSON descriptor whose
    staged file is a decodable WAV."""
    r = client.post(
        "/v1/audio/key-match",
        json={
            "file_path": staged_audio,
            "target_key": "C",
            "output_path": "out/key.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/key.wav"
    assert body["size"] > 100

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_key_match_json_metadata(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries ``source_key``, ``target_key`` and ``semitones``."""
    r = client.post(
        "/v1/audio/key-match",
        json={
            "file_path": staged_audio,
            "target_key": "G",
            "output_path": "key/matched.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("source_key")
    assert body.get("target_key")
    assert "semitones" in body


def test_key_match_sharp_key(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Sharp accidentals (e.g. F#) are accepted."""
    r = client.post(
        "/v1/audio/key-match",
        json={
            "file_path": staged_audio,
            "target_key": "F#",
            "output_path": "out/key_sharp.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_key_match_flat_key(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Flat accidentals (e.g. Bb) are accepted."""
    r = client.post(
        "/v1/audio/key-match",
        json={
            "file_path": staged_audio,
            "target_key": "Bb",
            "output_path": "out/key_flat.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_key_match_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_format=mp3`` stages an MP3 instead of WAV."""
    r = client.post(
        "/v1/audio/key-match",
        json={
            "file_path": staged_audio,
            "target_key": "A",
            "output_format": "mp3",
            "output_path": "out/key.mp3",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_key_match_invalid_key_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``target_key`` outside the recognised note set → 400."""
    r = client.post(
        "/v1/audio/key-match",
        json={
            "file_path": staged_audio,
            "target_key": "Z",
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_key_match_missing_key_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing required ``target_key`` → 422."""
    r = client.post(
        "/v1/audio/key-match",
        json={
            "file_path": staged_audio,
            "output_path": "out/missing.wav",
        },
    )
    assert r.status_code == 422, r.text


def test_key_match_missing_file(client: httpx.Client) -> None:
    """Reference to a missing file → 400/404/422."""
    r = client.post(
        "/v1/audio/key-match",
        json={
            "file_path": "no/such.wav",
            "target_key": "C",
            "output_path": "out/ghost.wav",
        },
    )
    assert r.status_code in (400, 404, 422), r.text
