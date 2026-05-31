"""Unit tests for MidiComposeEngine — pure JSON-to-MIDI transcoder.

These tests exercise the validation path (bad specs → MidiComposeError)
and round-trip (good spec → valid SMF that mido can re-read). No
fluidsynth dependency here — that's covered by the integration suite
which uses the prod image."""

from __future__ import annotations

import io

import mido
import pytest

from audiolla.engines.midi_compose import MidiComposeEngine, MidiComposeError


def _engine() -> MidiComposeEngine:
    return MidiComposeEngine(slug="midi-compose", entry={"executor": "midi_compose"})


# ── happy path ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compose_minimal_spec_returns_valid_smf():
    spec = {
        "tempo_bpm": 120,
        "tracks": [
            {"program": 0, "channel": 0, "notes": [
                {"pitch": 60, "start_beats": 0.0, "duration_beats": 1.0, "velocity": 100},
            ]},
        ],
    }
    midi_bytes = await _engine().compose(spec)
    # Standard MIDI File magic header.
    assert midi_bytes.startswith(b"MThd"), "missing MThd header"
    # Round-trip through mido — confirms structural validity.
    mid = mido.MidiFile(file=io.BytesIO(midi_bytes))
    assert mid.type == 1
    assert mid.ticks_per_beat == 480
    # Track 0 = tempo, track 1 = our note.
    assert len(mid.tracks) == 2
    msg_types = [m.type for m in mid.tracks[1] if not m.is_meta]
    assert "note_on" in msg_types
    assert "note_off" in msg_types


@pytest.mark.asyncio
async def test_compose_multi_track_multi_note():
    spec = {
        "tempo_bpm": 90,
        "tracks": [
            {"name": "Lead", "program": 0, "channel": 0, "notes": [
                {"pitch": 60, "start_beats": 0.0, "duration_beats": 0.5, "velocity": 100},
                {"pitch": 64, "start_beats": 0.5, "duration_beats": 0.5, "velocity": 100},
                {"pitch": 67, "start_beats": 1.0, "duration_beats": 1.0, "velocity": 100},
            ]},
            {"name": "Drums", "program": 0, "channel": 9, "notes": [
                {"pitch": 36, "start_beats": 0.0, "duration_beats": 0.1, "velocity": 110},
                {"pitch": 38, "start_beats": 1.0, "duration_beats": 0.1, "velocity": 100},
            ]},
        ],
    }
    midi_bytes = await _engine().compose(spec)
    mid = mido.MidiFile(file=io.BytesIO(midi_bytes))
    # 1 tempo track + 2 music tracks
    assert len(mid.tracks) == 3
    # Each music track has a track_name meta event we set.
    names = [
        next((m.name for m in t if m.type == "track_name"), None)
        for t in mid.tracks[1:]
    ]
    assert names == ["Lead", "Drums"]


@pytest.mark.asyncio
async def test_compose_tempo_and_time_signature_in_smf():
    spec = {
        "tempo_bpm": 200,
        "time_signature": [3, 4],
        "tracks": [
            {"program": 0, "channel": 0, "notes": [
                {"pitch": 60, "start_beats": 0.0, "duration_beats": 1.0, "velocity": 100},
            ]},
        ],
    }
    midi_bytes = await _engine().compose(spec)
    mid = mido.MidiFile(file=io.BytesIO(midi_bytes))
    set_tempo = next(m for m in mid.tracks[0] if m.type == "set_tempo")
    assert mido.tempo2bpm(set_tempo.tempo) == pytest.approx(200.0, rel=1e-3)
    ts = next(m for m in mid.tracks[0] if m.type == "time_signature")
    assert ts.numerator == 3 and ts.denominator == 4


@pytest.mark.asyncio
async def test_compose_optional_key_signature():
    spec = {
        "tempo_bpm": 120,
        "key_signature": "Am",
        "tracks": [
            {"program": 0, "channel": 0, "notes": [
                {"pitch": 69, "start_beats": 0.0, "duration_beats": 1.0, "velocity": 100},
            ]},
        ],
    }
    midi_bytes = await _engine().compose(spec)
    mid = mido.MidiFile(file=io.BytesIO(midi_bytes))
    ks = next(m for m in mid.tracks[0] if m.type == "key_signature")
    assert ks.key == "Am"


@pytest.mark.asyncio
async def test_compose_program_change_emitted():
    """Each track must emit a program_change before the first note so
    the synth picks up the right GM patch."""
    spec = {
        "tempo_bpm": 120,
        "tracks": [
            {"program": 40, "channel": 0, "notes": [
                {"pitch": 60, "start_beats": 0.0, "duration_beats": 0.5, "velocity": 100},
            ]},
        ],
    }
    midi_bytes = await _engine().compose(spec)
    mid = mido.MidiFile(file=io.BytesIO(midi_bytes))
    pc = next(m for m in mid.tracks[1] if m.type == "program_change")
    assert pc.program == 40
    assert pc.channel == 0


# ── validation: bad top-level shape ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_compose_rejects_non_object_spec():
    with pytest.raises(MidiComposeError, match="must be a JSON object"):
        await _engine().compose([])  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_compose_rejects_missing_tracks():
    with pytest.raises(MidiComposeError, match="tracks"):
        await _engine().compose({"tempo_bpm": 120})


@pytest.mark.asyncio
async def test_compose_rejects_empty_tracks():
    with pytest.raises(MidiComposeError, match="non-empty"):
        await _engine().compose({"tempo_bpm": 120, "tracks": []})


# ── validation: tempo + time signature ───────────────────────────────────────

@pytest.mark.asyncio
async def test_compose_rejects_tempo_zero():
    with pytest.raises(MidiComposeError, match="tempo_bpm"):
        await _engine().compose({
            "tempo_bpm": 0,
            "tracks": [{"program": 0, "channel": 0, "notes": []}],
        })


@pytest.mark.asyncio
async def test_compose_rejects_bad_time_signature():
    with pytest.raises(MidiComposeError, match="time_signature"):
        await _engine().compose({
            "tempo_bpm": 120,
            "time_signature": [4, 3],  # denominator must be power of 2
            "tracks": [{"program": 0, "channel": 0, "notes": []}],
        })


@pytest.mark.asyncio
async def test_compose_rejects_bad_key_signature():
    with pytest.raises(MidiComposeError, match="key_signature"):
        await _engine().compose({
            "tempo_bpm": 120,
            "key_signature": "H#mmm",
            "tracks": [{"program": 0, "channel": 0, "notes": []}],
        })


# ── validation: notes ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_compose_rejects_pitch_out_of_range():
    with pytest.raises(MidiComposeError, match=r"\.pitch.*\[0, 127\]"):
        await _engine().compose({
            "tempo_bpm": 120,
            "tracks": [{"program": 0, "channel": 0, "notes": [
                {"pitch": 200, "start_beats": 0, "duration_beats": 1, "velocity": 100},
            ]}],
        })


@pytest.mark.asyncio
async def test_compose_rejects_negative_start():
    with pytest.raises(MidiComposeError, match="start_beats"):
        await _engine().compose({
            "tempo_bpm": 120,
            "tracks": [{"program": 0, "channel": 0, "notes": [
                {"pitch": 60, "start_beats": -1, "duration_beats": 1, "velocity": 100},
            ]}],
        })


@pytest.mark.asyncio
async def test_compose_rejects_zero_duration():
    with pytest.raises(MidiComposeError, match="duration_beats"):
        await _engine().compose({
            "tempo_bpm": 120,
            "tracks": [{"program": 0, "channel": 0, "notes": [
                {"pitch": 60, "start_beats": 0, "duration_beats": 0, "velocity": 100},
            ]}],
        })


@pytest.mark.asyncio
async def test_compose_rejects_bad_velocity():
    with pytest.raises(MidiComposeError, match="velocity"):
        await _engine().compose({
            "tempo_bpm": 120,
            "tracks": [{"program": 0, "channel": 0, "notes": [
                {"pitch": 60, "start_beats": 0, "duration_beats": 1, "velocity": 200},
            ]}],
        })


@pytest.mark.asyncio
async def test_compose_rejects_bad_program():
    with pytest.raises(MidiComposeError, match="program"):
        await _engine().compose({
            "tempo_bpm": 120,
            "tracks": [{"program": 999, "channel": 0, "notes": []}],
        })


@pytest.mark.asyncio
async def test_compose_rejects_bad_channel():
    with pytest.raises(MidiComposeError, match="channel"):
        await _engine().compose({
            "tempo_bpm": 120,
            "tracks": [{"program": 0, "channel": 17, "notes": []}],
        })


@pytest.mark.asyncio
async def test_compose_overlapping_same_pitch_orders_off_before_on():
    """Two notes on the same pitch back-to-back must end the first note
    before starting the second — otherwise the synth gets a stuck note."""
    spec = {
        "tempo_bpm": 120,
        "tracks": [{"program": 0, "channel": 0, "notes": [
            {"pitch": 60, "start_beats": 0.0, "duration_beats": 1.0, "velocity": 100},
            {"pitch": 60, "start_beats": 1.0, "duration_beats": 1.0, "velocity": 100},
        ]}],
    }
    midi_bytes = await _engine().compose(spec)
    mid = mido.MidiFile(file=io.BytesIO(midi_bytes))
    # Walk events in absolute-time order across the track.
    abs_time = 0
    sequence = []
    for msg in mid.tracks[1]:
        abs_time += msg.time
        if msg.type in ("note_on", "note_off"):
            sequence.append((abs_time, msg.type, msg.note))
    # Find the tick where note 60 retriggers; the note_off must come first.
    at_one_beat = [e for e in sequence if e[0] == mid.ticks_per_beat]
    types = [e[1] for e in at_one_beat]
    assert types == ["note_off", "note_on"], types
