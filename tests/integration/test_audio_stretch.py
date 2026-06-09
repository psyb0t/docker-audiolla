"""End-to-end test for ``POST /v1/audio/stretch``.

Time-stretch (``tempo_factor``) and/or pitch-shift (``pitch_semitones``)
via the stretch engine. Both factors default to identity. CPU-only DSP.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_audio_decodable, assert_mp3, assert_wav

pytestmark = pytest.mark.engine("stretch")


def test_stretch_identity(
    client: httpx.Client, staged_audio: str,
) -> None:
    """No tempo/pitch change → still returns a decodable WAV."""
    r = client.post(
        "/v1/audio/stretch",
        json={
            "file_path": staged_audio,
            "output_path": "out/stretch_id.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/stretch_id.wav"
    assert body["size"] > 100

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_stretch_tempo_factor(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``tempo_factor=0.5`` should roughly double duration. We compare
    decoded durations: out > orig * 1.5 (with margin)."""
    src = client.get(f"/v1/files/{staged_audio}")
    assert src.status_code == 200
    import io
    import soundfile as sf  # noqa: PLC0415
    with sf.SoundFile(io.BytesIO(src.content)) as f:
        dur_orig = len(f) / f.samplerate

    r = client.post(
        "/v1/audio/stretch",
        json={
            "file_path": staged_audio,
            "tempo_factor": 0.5,
            "output_path": "out/stretch_slow.wav",
        },
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{r.json()['path']}")
    with sf.SoundFile(io.BytesIO(fetched.content)) as f:
        dur_slow = len(f) / f.samplerate
    assert dur_slow > dur_orig * 1.5, (
        f"slow file not stretched (orig={dur_orig:.2f}s slow={dur_slow:.2f}s)"
    )


def test_stretch_pitch_semitones(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``pitch_semitones=12`` (octave up) → 200 with decodable audio."""
    r = client.post(
        "/v1/audio/stretch",
        json={
            "file_path": staged_audio,
            "pitch_semitones": 12,
            "output_path": "out/stretch_pitch.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert_audio_decodable(fetched.content)


def test_stretch_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_format=mp3`` stages an MP3."""
    r = client.post(
        "/v1/audio/stretch",
        json={
            "file_path": staged_audio,
            "output_format": "mp3",
            "output_path": "out/stretch.mp3",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/stretch.mp3"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_stretch_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_path`` is honoured; staged file is a valid WAV."""
    r = client.post(
        "/v1/audio/stretch",
        json={
            "file_path": staged_audio,
            "tempo_factor": 1.25,
            "output_path": "stretch/fast.wav",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == "stretch/fast.wav"

    fetched = client.get("/v1/files/stretch/fast.wav")
    assert fetched.status_code == 200
    assert_wav(fetched.content)


def test_stretch_combined(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Tempo and pitch change combined → 200 with decodable WAV."""
    r = client.post(
        "/v1/audio/stretch",
        json={
            "file_path": staged_audio,
            "tempo_factor": 0.8,
            "pitch_semitones": -3,
            "output_path": "out/stretch_combo.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert_wav(fetched.content)
