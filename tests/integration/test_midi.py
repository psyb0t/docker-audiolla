"""End-to-end tests for the MIDI compose / render / generate suite.

Covers ``POST /v1/midi/compose``, ``POST /v1/midi/render``,
``POST /v1/midi/generate``. Compose takes a JSON song spec, produces a
Standard MIDI File; render takes a staged MIDI file and produces audio
via fluidsynth + SoundFont; generate is the one-shot composition that
chains compose + render.
"""

from __future__ import annotations

import secrets

import httpx
import pytest

from .helpers import assert_mp3, assert_midi, assert_wav

pytestmark = pytest.mark.engine("midi-compose", "midi-render")


SPEC = {
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
                {"pitch": 72, "start_beats": 1.5, "duration_beats": 0.5, "velocity": 100},
            ],
        },
        {
            "name": "Drums",
            "program": 0,
            "channel": 9,
            "notes": [
                {"pitch": 36, "start_beats": 0.0, "duration_beats": 0.1, "velocity": 110},
                {"pitch": 36, "start_beats": 1.0, "duration_beats": 0.1, "velocity": 110},
                {"pitch": 36, "start_beats": 2.0, "duration_beats": 0.1, "velocity": 110},
                {"pitch": 36, "start_beats": 3.0, "duration_beats": 0.1, "velocity": 110},
            ],
        },
    ],
}


def _stage_composed_midi(client: httpx.Client, dest: str) -> None:
    """Compose the demo SPEC and write the result into ``dest`` under /v1/files."""
    r = client.post(
        "/v1/midi/compose",
        params={"output_path": dest},
        json=SPEC,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == dest


# ── compose ────────────────────────────────────────────────────────────────


def test_midi_compose_output_path(client: httpx.Client) -> None:
    """compose with output_path stages a real MThd file under /v1/files."""
    dest = f"midi/song-{secrets.token_hex(4)}.mid"
    r = client.post(
        "/v1/midi/compose",
        params={"output_path": dest},
        json=SPEC,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == dest
    assert body["size"] >= 50

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_midi(fetched.content, min_bytes=50)


def test_midi_compose_bad_pitch_400(client: httpx.Client) -> None:
    """Out-of-range pitch (200) → 400 with detail mentioning pitch."""
    r = client.post(
        "/v1/midi/compose",
        params={"output_path": "midi/bad.mid"},
        json={
            "tempo_bpm": 120,
            "tracks": [{
                "program": 0,
                "channel": 0,
                "notes": [
                    {"pitch": 200, "start_beats": 0, "duration_beats": 1, "velocity": 100}
                ],
            }],
        },
    )
    assert r.status_code == 400, r.text
    assert "pitch" in r.text.lower()


# ── render ────────────────────────────────────────────────────────────────


def test_midi_render_returns_audio(client: httpx.Client) -> None:
    """Compose then render via file_path → staged WAV."""
    src = f"midi/in-{secrets.token_hex(4)}.mid"
    _stage_composed_midi(client, src)
    dest = f"midi/rendered-{secrets.token_hex(4)}.wav"

    r = client.post(
        "/v1/midi/render",
        json={
            "file_path": src,
            "output_format": "wav",
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == dest

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=1000)


def test_midi_render_with_mp3_output(client: httpx.Client) -> None:
    """Render with output_format=mp3 → staged MP3."""
    src = f"midi/in-{secrets.token_hex(4)}.mid"
    _stage_composed_midi(client, src)
    dest = f"midi/rendered-{secrets.token_hex(4)}.mp3"

    r = client.post(
        "/v1/midi/render",
        json={
            "file_path": src,
            "output_format": "mp3",
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_midi_render_non_midi_400(client: httpx.Client) -> None:
    """Render rejects non-MIDI bytes with 400 + MThd in the detail."""
    bogus = f"uploads/not-midi-{secrets.token_hex(4)}.bin"
    put = client.put(
        f"/v1/files/{bogus}",
        content=b"not a midi file at all",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert put.status_code in (200, 201)

    r = client.post(
        "/v1/midi/render",
        json={
            "file_path": bogus,
            "output_path": f"midi/rendered-{secrets.token_hex(4)}.wav",
        },
    )
    assert r.status_code == 400, r.text
    assert "mthd" in r.text.lower()


# ── generate (compose + render in one call) ────────────────────────────────


def test_midi_generate_output_path(client: httpx.Client) -> None:
    """generate with output_path stages a real RIFF/WAVE file."""
    dest = f"midi/generated-{secrets.token_hex(4)}.wav"
    r = client.post(
        "/v1/midi/generate",
        params={"output_format": "wav", "output_path": dest},
        json=SPEC,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == dest

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=1000)
