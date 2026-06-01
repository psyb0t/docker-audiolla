"""Unit tests for MidiComposeEngine.inspect() and .transform().

These are pure-Python (mido only) so they run in the dev container.
End-to-end fluidsynth playback of the transformed output is covered by
the integration suite."""

from __future__ import annotations

import io

import mido
import pytest

from audiolla.engines.midi_compose import MidiComposeEngine, MidiComposeError


def _engine() -> MidiComposeEngine:
    return MidiComposeEngine(slug="midi-compose", entry={"executor": "midi_compose"})


def _build_demo_midi() -> bytes:
    """Two tracks: a C major arpeggio on channel 0 + a kick on channel 9.
    Calls the engine's _compose_sync directly so this helper is callable
    from both sync setup and async test bodies."""
    spec = {
        "tempo_bpm": 120,
        "time_signature": [4, 4],
        "tracks": [
            {"name": "Lead", "program": 0, "channel": 0, "notes": [
                {"pitch": 60, "start_beats": 0.0, "duration_beats": 0.5, "velocity": 100},
                {"pitch": 64, "start_beats": 0.5, "duration_beats": 0.5, "velocity": 100},
                {"pitch": 67, "start_beats": 1.0, "duration_beats": 0.5, "velocity": 100},
            ]},
            {"name": "Kick", "program": 0, "channel": 9, "notes": [
                {"pitch": 36, "start_beats": 0.0, "duration_beats": 0.1, "velocity": 110},
                {"pitch": 36, "start_beats": 1.0, "duration_beats": 0.1, "velocity": 110},
            ]},
        ],
    }
    return _engine()._compose_sync(spec)


# ── inspect ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_inspect_returns_structure():
    midi_bytes = _build_demo_midi()
    info = await _engine().inspect(midi_bytes)

    assert info["type"] == 1
    assert info["ticks_per_beat"] == 480
    assert info["size_bytes"] == len(midi_bytes)
    assert info["track_count"] == 3  # tempo track + 2 music tracks
    assert len(info["tempo_changes"]) >= 1
    assert abs(info["tempo_changes"][0]["bpm"] - 120.0) < 0.01
    assert info["time_signatures"][0]["numerator"] == 4
    assert info["time_signatures"][0]["denominator"] == 4

    # Lead track has 3 note_ons.
    lead = next(t for t in info["tracks"] if t["name"] == "Lead")
    assert lead["note_on_count"] == 3
    assert lead["channels"] == [0]
    assert lead["programs"] == [0]

    # Kick on channel 9.
    kick = next(t for t in info["tracks"] if t["name"] == "Kick")
    assert kick["channels"] == [9]


@pytest.mark.asyncio
async def test_inspect_rejects_empty_bytes():
    with pytest.raises(MidiComposeError, match="empty"):
        await _engine().inspect(b"")


@pytest.mark.asyncio
async def test_inspect_rejects_non_midi():
    with pytest.raises(MidiComposeError, match="MThd"):
        await _engine().inspect(b"RIFF" + b"\x00" * 100)


@pytest.mark.asyncio
async def test_inspect_rejects_corrupt_smf():
    """An SMF header followed by truncated body should fail cleanly,
    not stack-trace into mido internals."""
    with pytest.raises(MidiComposeError, match="failed to parse"):
        # MThd header but wrong body length.
        await _engine().inspect(b"MThd\x00\x00\x00\x06" + b"\x00\x01\x00\x01\x01\xe0" + b"X" * 10)


# ── transform: transpose ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transform_transpose_shifts_lead_not_drums():
    midi_bytes = _build_demo_midi()
    out = await _engine().transform(midi_bytes, transpose_semitones=12)

    mid = mido.MidiFile(file=io.BytesIO(out))
    # Lead track notes should be +12; Kick (channel 9) notes unchanged.
    lead_notes: list[int] = []
    kick_notes: list[int] = []
    for trk in mid.tracks:
        for msg in trk:
            if msg.type == "note_on" and msg.velocity > 0:
                if msg.channel == 0:
                    lead_notes.append(msg.note)
                elif msg.channel == 9:
                    kick_notes.append(msg.note)

    assert lead_notes == [72, 76, 79]  # was 60, 64, 67
    assert kick_notes == [36, 36]  # drums not transposed


@pytest.mark.asyncio
async def test_transform_transpose_drops_out_of_range_at_boundary():
    """Transposing past MIDI range should drop the offending notes,
    not wrap or clip silently. transpose_semitones is capped at ±48 so
    we build a spec with high notes that overflow at exactly +48."""
    high_spec = {
        "tempo_bpm": 120,
        "tracks": [
            {"name": "High", "program": 0, "channel": 0, "notes": [
                # 79 (G5) + 48 = 127 — survives (just barely)
                {"pitch": 79, "start_beats": 0.0, "duration_beats": 0.5, "velocity": 100},
                # 80 (G#5) + 48 = 128 — dropped
                {"pitch": 80, "start_beats": 0.5, "duration_beats": 0.5, "velocity": 100},
                # 100 + 48 = 148 — dropped
                {"pitch": 100, "start_beats": 1.0, "duration_beats": 0.5, "velocity": 100},
            ]},
        ],
    }
    midi_bytes = _engine()._compose_sync(high_spec)
    out = await _engine().transform(midi_bytes, transpose_semitones=48)
    mid = mido.MidiFile(file=io.BytesIO(out))
    surviving_notes = [
        msg.note for trk in mid.tracks for msg in trk
        if msg.type == "note_on" and msg.velocity > 0
    ]
    # Only the 79 → 127 note survives.
    assert surviving_notes == [127], surviving_notes


@pytest.mark.asyncio
async def test_transform_rejects_extreme_transpose():
    """Transpose is capped at ±48 (4 octaves) — anything beyond is
    rejected at the engine boundary rather than silently clipped."""
    with pytest.raises(MidiComposeError, match="transpose"):
        await _engine().transform(_build_demo_midi(), transpose_semitones=200)
    with pytest.raises(MidiComposeError, match="transpose"):
        await _engine().transform(_build_demo_midi(), transpose_semitones=-49)


# ── transform: tempo override ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transform_tempo_override():
    midi_bytes = _build_demo_midi()
    out = await _engine().transform(midi_bytes, tempo_bpm=200)

    mid = mido.MidiFile(file=io.BytesIO(out))
    tempos = [
        mido.tempo2bpm(msg.tempo)
        for trk in mid.tracks for msg in trk
        if msg.type == "set_tempo"
    ]
    assert tempos, "no set_tempo events in output"
    assert all(abs(t - 200.0) < 0.01 for t in tempos)


@pytest.mark.asyncio
async def test_transform_rejects_out_of_range_tempo():
    with pytest.raises(MidiComposeError, match="tempo_bpm"):
        await _engine().transform(_build_demo_midi(), tempo_bpm=0.0)
    with pytest.raises(MidiComposeError, match="tempo_bpm"):
        await _engine().transform(_build_demo_midi(), tempo_bpm=9999.0)


# ── transform: channel filtering ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transform_keep_channels_drops_others():
    midi_bytes = _build_demo_midi()
    out = await _engine().transform(midi_bytes, keep_channels=[0])

    mid = mido.MidiFile(file=io.BytesIO(out))
    channels = {
        msg.channel
        for trk in mid.tracks for msg in trk
        if msg.type in ("note_on", "note_off")
    }
    assert channels == {0}


@pytest.mark.asyncio
async def test_transform_drop_channels_removes_drums():
    midi_bytes = _build_demo_midi()
    out = await _engine().transform(midi_bytes, drop_channels=[9])

    mid = mido.MidiFile(file=io.BytesIO(out))
    channels = {
        msg.channel
        for trk in mid.tracks for msg in trk
        if msg.type in ("note_on", "note_off")
    }
    assert 9 not in channels


@pytest.mark.asyncio
async def test_transform_rejects_both_keep_and_drop():
    with pytest.raises(MidiComposeError, match="not both"):
        await _engine().transform(
            _build_demo_midi(),
            keep_channels=[0],
            drop_channels=[9],
        )


# ── transform: quantize ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_transform_quantize_snaps_note_starts():
    """A 16th-note grid (0.25 beats) should keep our 0.0 / 0.5 / 1.0
    note starts unchanged (they're already grid-aligned) but still
    produce a parseable SMF without errors."""
    out = await _engine().transform(_build_demo_midi(), quantize_grid_beats=0.25)
    mid = mido.MidiFile(file=io.BytesIO(out))
    assert sum(
        1 for trk in mid.tracks for m in trk
        if m.type == "note_on" and m.velocity > 0
    ) == 5  # 3 lead + 2 kick


@pytest.mark.asyncio
async def test_transform_rejects_zero_quantize():
    with pytest.raises(MidiComposeError, match="quantize_grid_beats"):
        await _engine().transform(_build_demo_midi(), quantize_grid_beats=0)


# ── transform: identity = same content ───────────────────────────────────────


@pytest.mark.asyncio
async def test_transform_with_no_args_preserves_notes():
    midi_bytes = _build_demo_midi()
    out = await _engine().transform(midi_bytes)
    # Same note count, same channels, same pitches.
    orig_notes = sorted(
        (m.channel, m.note)
        for trk in mido.MidiFile(file=io.BytesIO(midi_bytes)).tracks
        for m in trk if m.type == "note_on" and m.velocity > 0
    )
    new_notes = sorted(
        (m.channel, m.note)
        for trk in mido.MidiFile(file=io.BytesIO(out)).tracks
        for m in trk if m.type == "note_on" and m.velocity > 0
    )
    assert orig_notes == new_notes
