"""End-to-end test for ``POST /v1/audio/to_midi/basic-pitch``.

Polyphonic audio-to-MIDI transcription via Spotify basic-pitch (ONNX
backend, bundled in the prod image). CPU-only.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_midi

pytestmark = pytest.mark.engine("basic-pitch")


def test_to_midi_returns_midi_bytes(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Happy path: the staged blob is a SMF (MThd header)."""
    r = client.post(
        "/v1/audio/to_midi/basic-pitch",
        json={
            "file_path": staged_audio,
            "output_path": "out/bp.mid",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/bp.mid"
    assert body["engine"] == "basic-pitch"
    assert body["size"] >= 10

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_midi(fetched.content, min_bytes=10)


def test_to_midi_onset_threshold(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``onset_threshold`` is accepted."""
    r = client.post(
        "/v1/audio/to_midi/basic-pitch",
        json={
            "file_path": staged_audio,
            "onset_threshold": 0.8,
            "output_path": "out/bp_onset.mid",
        },
    )
    assert r.status_code == 200, r.text


def test_to_midi_frame_threshold(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``frame_threshold`` is accepted."""
    r = client.post(
        "/v1/audio/to_midi/basic-pitch",
        json={
            "file_path": staged_audio,
            "frame_threshold": 0.2,
            "output_path": "out/bp_frame.mid",
        },
    )
    assert r.status_code == 200, r.text


def test_to_midi_minimum_note_length_ms(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``minimum_note_length_ms`` is accepted."""
    r = client.post(
        "/v1/audio/to_midi/basic-pitch",
        json={
            "file_path": staged_audio,
            "minimum_note_length_ms": 120,
            "output_path": "out/bp_min.mid",
        },
    )
    assert r.status_code == 200, r.text


def test_to_midi_frequency_range(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``minimum_frequency`` + ``maximum_frequency`` accepted together."""
    r = client.post(
        "/v1/audio/to_midi/basic-pitch",
        json={
            "file_path": staged_audio,
            "minimum_frequency": 100,
            "maximum_frequency": 2000,
            "output_path": "out/bp_freq.mid",
        },
    )
    assert r.status_code == 200, r.text


def test_to_midi_multiple_pitch_bends(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``multiple_pitch_bends=true`` accepted."""
    r = client.post(
        "/v1/audio/to_midi/basic-pitch",
        json={
            "file_path": staged_audio,
            "multiple_pitch_bends": True,
            "output_path": "out/bp_pb.mid",
        },
    )
    assert r.status_code == 200, r.text


def test_to_midi_melodia_trick_false(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``melodia_trick=false`` accepted."""
    r = client.post(
        "/v1/audio/to_midi/basic-pitch",
        json={
            "file_path": staged_audio,
            "melodia_trick": False,
            "output_path": "out/bp_melodia.mid",
        },
    )
    assert r.status_code == 200, r.text


def test_to_midi_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_path`` is honoured; staged file is a valid MIDI."""
    r = client.post(
        "/v1/audio/to_midi/basic-pitch",
        json={
            "file_path": staged_audio,
            "output_path": "midi/transcribed.mid",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == "midi/transcribed.mid"

    fetched = client.get("/v1/files/midi/transcribed.mid")
    assert fetched.status_code == 200
    assert_midi(fetched.content)


def test_to_midi_is_deterministic(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Same input → same output size (basic-pitch is deterministic at
    fixed thresholds)."""
    r1 = client.post(
        "/v1/audio/to_midi/basic-pitch",
        json={
            "file_path": staged_audio,
            "output_path": "out/bp_det_1.mid",
        },
    )
    r2 = client.post(
        "/v1/audio/to_midi/basic-pitch",
        json={
            "file_path": staged_audio,
            "output_path": "out/bp_det_2.mid",
        },
    )
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    f1 = client.get(f"/v1/files/{r1.json()['path']}")
    f2 = client.get(f"/v1/files/{r2.json()['path']}")
    assert len(f1.content) == len(f2.content), (
        f"non-deterministic output: {len(f1.content)} vs {len(f2.content)}"
    )


def test_to_midi_wrong_engine_type(
    client: httpx.Client, staged_audio: str,
) -> None:
    """A loaded engine that isn't a basic-pitch engine → 400 or 404
    (404 when not in this container's enabled set; 400 when present but
    wrong type)."""
    r = client.post(
        "/v1/audio/to_midi/silence-detect",
        json={
            "file_path": staged_audio,
            "output_path": "out/bp_wrong.mid",
        },
    )
    assert r.status_code in (400, 404), r.text
