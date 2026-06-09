"""End-to-end test for ``POST /v1/audio/chords-to-midi``.

Detects the chord progression via the chord-detect engine and exports
each chord segment as a held chord (root + third + fifth) in a Standard
MIDI File. Pure CPU.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_midi

pytestmark = pytest.mark.engine("chord-detect")


def test_chords_to_midi_returns_midi(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Happy path: the staged blob is a SMF (MThd header)."""
    r = client.post(
        "/v1/audio/chords-to-midi",
        json={
            "file_path": staged_audio,
            "output_path": "out/chords.mid",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/chords.mid"
    assert body["size"] >= 50

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_midi(fetched.content, min_bytes=50)


def test_chords_to_midi_staged_response(
    client: httpx.Client, staged_audio: str,
) -> None:
    """JSON response includes ``chord_count`` (>0) and the ``path`` echo."""
    r = client.post(
        "/v1/audio/chords-to-midi",
        json={
            "file_path": staged_audio,
            "output_path": "ctm_test/chords.mid",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "ctm_test/chords.mid"
    assert body.get("chord_count", 0) > 0


def test_chords_to_midi_custom_octave(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Custom ``octave`` and ``velocity`` accepted."""
    r = client.post(
        "/v1/audio/chords-to-midi",
        json={
            "file_path": staged_audio,
            "octave": 5,
            "velocity": 100,
            "output_path": "out/chords_oct5.mid",
        },
    )
    assert r.status_code == 200, r.text


def test_chords_to_midi_invalid_velocity(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``velocity > 127`` rejected by handler-level guard."""
    r = client.post(
        "/v1/audio/chords-to-midi",
        json={
            "file_path": staged_audio,
            "velocity": 200,
            "output_path": "out/bad.mid",
        },
    )
    assert r.status_code in (400, 422), r.text
