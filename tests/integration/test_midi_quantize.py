"""End-to-end test for ``POST /v1/midi/quantize``.

Snaps note start times to a beat grid (default 0.25 beats == 16th notes).
"""

from __future__ import annotations

import secrets

import httpx
import pytest

from .helpers import assert_midi

pytestmark = pytest.mark.engine("midi-compose")


_COMPOSE_SPEC = {
    "tempo_bpm": 120,
    "time_signature": [4, 4],
    "tracks": [
        {
            "name": "Lead",
            "program": 0,
            "channel": 0,
            "notes": [
                {"pitch": 60, "start_beats": 0.0, "duration_beats": 0.5, "velocity": 100},
                {"pitch": 64, "start_beats": 0.5, "duration_beats": 0.5, "velocity": 100},
                {"pitch": 67, "start_beats": 1.0, "duration_beats": 0.5, "velocity": 100},
            ],
        },
    ],
}


def _stage_midi(client: httpx.Client) -> str:
    dest = f"midi/qz-in-{secrets.token_hex(4)}.mid"
    r = client.post("/v1/midi/compose", params={"output_path": dest}, json=_COMPOSE_SPEC)
    assert r.status_code == 200, r.text
    return dest


def test_quantize_default_grid(client: httpx.Client) -> None:
    """Default grid (0.25 beats) returns a valid MIDI file."""
    src = _stage_midi(client)
    dest = f"midi/qz-out-{secrets.token_hex(4)}.mid"
    r = client.post(
        "/v1/midi/quantize",
        json={"file_path": src, "output_path": dest},
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_midi(fetched.content)


def test_quantize_eighth_grid(client: httpx.Client) -> None:
    """grid_beats=0.5 (8th-note grid) accepted."""
    src = _stage_midi(client)
    dest = f"midi/qz-out-{secrets.token_hex(4)}.mid"
    r = client.post(
        "/v1/midi/quantize",
        json={"file_path": src, "grid_beats": 0.5, "output_path": dest},
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{dest}")
    assert_midi(fetched.content)


def test_quantize_zero_grid_400(client: httpx.Client) -> None:
    """grid_beats=0 is invalid → 400."""
    src = _stage_midi(client)
    r = client.post(
        "/v1/midi/quantize",
        json={
            "file_path": src,
            "grid_beats": 0,
            "output_path": f"midi/qz-{secrets.token_hex(4)}.mid",
        },
    )
    assert r.status_code == 400, r.text


def test_quantize_non_midi_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """WAV input → 400."""
    r = client.post(
        "/v1/midi/quantize",
        json={
            "file_path": staged_audio,
            "output_path": f"midi/qz-{secrets.token_hex(4)}.mid",
        },
    )
    assert r.status_code == 400, r.text


def test_quantize_output_path_response(client: httpx.Client) -> None:
    """Response includes the explicit output_path back to caller."""
    src = _stage_midi(client)
    dest = f"midi/qz-explicit-{secrets.token_hex(4)}.mid"
    r = client.post(
        "/v1/midi/quantize",
        json={"file_path": src, "output_path": dest},
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == dest

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_midi(fetched.content)
