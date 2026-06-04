"""JSON-to-MIDI transcoder (mido 1.3.3, MIT).

Takes a JSON song spec and writes a Type-1 multi-track MIDI file. The
spec is designed to be the simplest thing an LLM agent can emit and the
audiolla server can validate:

    {
      "tempo_bpm": 120,                       (optional, default 120)
      "time_signature": [4, 4],               (optional, default [4, 4])
      "key_signature": "C",                   (optional, e.g. "C", "Am")
      "ticks_per_beat": 480,                  (optional, default 480)
      "tracks": [
        {
          "name": "Lead",                     (optional)
          "program": 0,                       (GM program 0–127, default 0)
          "channel": 0,                       (0–15, channel 9 = drums)
          "volume": 100,                      (0–127, default 100 — CC#7)
          "pan": 64,                          (0–127, default 64 — CC#10)
          "notes": [
            {"pitch": 60,                     (0–127, 60 = middle C)
             "start_beats": 0.0,              (>= 0)
             "duration_beats": 0.5,           (> 0)
             "velocity": 100}                 (0–127, default 100)
          ]
        }
      ]
    }

Time is in beats — the engine converts to ticks using ``ticks_per_beat``
on the way out. The resulting file plays back at ``tempo_bpm`` until
overridden by the host (DAWs / synths respect the tempo meta-event).

No model weights — ``get_model()`` is a no-op. CPU-only. Validation is
fail-loud: bad pitch / negative duration / unknown program returns a
clean :class:`MidiComposeError` with the offending path inside the spec.
"""

from __future__ import annotations

import asyncio
import io
import re
from typing import Any

from ..audio import AudioConversionError
from .base import EngineBase

_KEY_SIG_RE = re.compile(r"^[A-G][#b]?m?$")


class MidiComposeError(AudioConversionError):
    """Spec rejected during validation or MIDI writing failed."""


_DRUM_NOTE_MAP: dict[str, int] = {
    "kick": 36,
    "snare": 38,
    "hihat": 42,
    "hihat_closed": 42,
    "hihat_open": 46,
    "ride": 51,
    "crash": 49,
    "tom_high": 50,
    "tom_mid": 47,
    "tom_low": 45,
    "clap": 39,
    "rim": 37,
    "cowbell": 56,
    "tambourine": 54,
    "shaker": 69,
    "wood_block": 76,
}


def _bounded_int(name: str, value: Any, lo: int, hi: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise MidiComposeError(f"{name} must be an integer, got {value!r}")
    if value < lo or value > hi:
        raise MidiComposeError(f"{name} must be in [{lo}, {hi}], got {value}")
    return value


def _bounded_float(name: str, value: Any, lo: float, hi: float | None) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise MidiComposeError(f"{name} must be a number, got {value!r}")
    v = float(value)
    if v < lo:
        raise MidiComposeError(f"{name} must be >= {lo}, got {v}")
    if hi is not None and v > hi:
        raise MidiComposeError(f"{name} must be <= {hi}, got {v}")
    return v


class MidiComposeEngine(EngineBase):
    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)

    async def compose(self, spec: dict[str, Any]) -> bytes:
        async with self._lock:
            result = await asyncio.to_thread(self._compose_sync, spec)
            self._touch()
            return result

    def _compose_sync(self, spec: dict[str, Any]) -> bytes:
        import mido

        if not isinstance(spec, dict):
            raise MidiComposeError("spec must be a JSON object")

        tempo_bpm = _bounded_float(
            "tempo_bpm", spec.get("tempo_bpm", 120), 1.0, 999.0,
        )
        ticks_per_beat = _bounded_int(
            "ticks_per_beat", spec.get("ticks_per_beat", 480), 24, 1920,
        )

        ts = spec.get("time_signature", [4, 4])
        if (
            not isinstance(ts, list)
            or len(ts) != 2
            or not all(isinstance(x, int) and not isinstance(x, bool) for x in ts)
        ):
            raise MidiComposeError(
                "time_signature must be [numerator, denominator] integers"
            )
        ts_num, ts_den = ts
        if ts_num < 1 or ts_num > 32:
            raise MidiComposeError(f"time_signature numerator out of range: {ts_num}")
        # MIDI stores denominator as a power-of-two exponent.
        if ts_den not in (1, 2, 4, 8, 16, 32):
            raise MidiComposeError(
                f"time_signature denominator must be 1/2/4/8/16/32, got {ts_den}"
            )

        key_sig = spec.get("key_signature")
        if key_sig is not None:
            if not isinstance(key_sig, str) or not _KEY_SIG_RE.match(key_sig):
                raise MidiComposeError(
                    f"key_signature {key_sig!r} must look like C, Am, F#, Bbm"
                )

        tracks = spec.get("tracks")
        if not isinstance(tracks, list) or not tracks:
            raise MidiComposeError("tracks must be a non-empty list")

        mid = mido.MidiFile(type=1, ticks_per_beat=ticks_per_beat)

        # Tempo track — global meta events live in track 0.
        tempo_track = mido.MidiTrack()
        tempo_track.append(mido.MetaMessage(
            "set_tempo",
            tempo=mido.bpm2tempo(tempo_bpm),
            time=0,
        ))
        tempo_track.append(mido.MetaMessage(
            "time_signature",
            numerator=ts_num,
            denominator=ts_den,
            time=0,
        ))
        if key_sig is not None:
            tempo_track.append(mido.MetaMessage(
                "key_signature", key=key_sig, time=0,
            ))
        mid.tracks.append(tempo_track)

        for tidx, t in enumerate(tracks):
            if not isinstance(t, dict):
                raise MidiComposeError(f"tracks[{tidx}] must be an object")
            name = t.get("name")
            program = _bounded_int(
                f"tracks[{tidx}].program", t.get("program", 0), 0, 127,
            )
            channel = _bounded_int(
                f"tracks[{tidx}].channel", t.get("channel", 0), 0, 15,
            )
            volume = _bounded_int(
                f"tracks[{tidx}].volume", t.get("volume", 100), 0, 127,
            )
            pan = _bounded_int(
                f"tracks[{tidx}].pan", t.get("pan", 64), 0, 127,
            )
            notes = t.get("notes")
            if not isinstance(notes, list):
                raise MidiComposeError(f"tracks[{tidx}].notes must be a list")

            track = mido.MidiTrack()
            if name:
                track.append(mido.MetaMessage("track_name", name=str(name), time=0))
            track.append(mido.Message(
                "program_change", channel=channel, program=program, time=0,
            ))
            track.append(mido.Message(
                "control_change", channel=channel, control=7, value=volume, time=0,
            ))
            track.append(mido.Message(
                "control_change", channel=channel, control=10, value=pan, time=0,
            ))

            # Collect (tick, message) pairs so we can convert absolute
            # positions to delta-ticks for MIDI's wire format.
            events: list[tuple[int, mido.Message]] = []
            for nidx, n in enumerate(notes):
                if not isinstance(n, dict):
                    raise MidiComposeError(
                        f"tracks[{tidx}].notes[{nidx}] must be an object"
                    )
                pitch = _bounded_int(
                    f"tracks[{tidx}].notes[{nidx}].pitch",
                    n.get("pitch"), 0, 127,
                )
                start_beats = _bounded_float(
                    f"tracks[{tidx}].notes[{nidx}].start_beats",
                    n.get("start_beats", 0.0), 0.0, None,
                )
                duration_beats = _bounded_float(
                    f"tracks[{tidx}].notes[{nidx}].duration_beats",
                    n.get("duration_beats"), 1.0 / 64.0, None,
                )
                velocity = _bounded_int(
                    f"tracks[{tidx}].notes[{nidx}].velocity",
                    n.get("velocity", 100), 1, 127,
                )
                on_tick = int(round(start_beats * ticks_per_beat))
                off_tick = int(round(
                    (start_beats + duration_beats) * ticks_per_beat
                ))
                if off_tick <= on_tick:
                    # Sub-tick durations round to zero — bump by 1 tick so
                    # the note actually plays. Document the lower bound.
                    off_tick = on_tick + 1
                events.append((on_tick, mido.Message(
                    "note_on", channel=channel, note=pitch,
                    velocity=velocity, time=0,
                )))
                events.append((off_tick, mido.Message(
                    "note_off", channel=channel, note=pitch,
                    velocity=0, time=0,
                )))

            # Sort by absolute tick; ties resolved by note_off before note_on
            # so back-to-back notes on the same pitch don't fight each other.
            def _sort_key(item: tuple[int, "mido.Message"]) -> tuple[int, int]:
                tick, msg = item
                # note_off (0) before note_on (1) at the same tick
                priority = 0 if msg.type == "note_off" else 1
                return (tick, priority)

            events.sort(key=_sort_key)

            prev_tick = 0
            for tick, msg in events:
                msg.time = tick - prev_tick
                track.append(msg)
                prev_tick = tick

            mid.tracks.append(track)

        buf = io.BytesIO()
        mid.save(file=buf)
        return buf.getvalue()

    # ── inspect: SMF bytes → JSON describing the file ──────────────────────

    async def inspect(self, midi_bytes: bytes) -> dict[str, Any]:
        """Parse a Standard MIDI File and return JSON describing its
        structure — tempo events, time signature, per-track note counts,
        program changes, total duration in beats + seconds."""
        async with self._lock:
            result = await asyncio.to_thread(self._inspect_sync, midi_bytes)
            self._touch()
            return result

    def _inspect_sync(self, midi_bytes: bytes) -> dict[str, Any]:
        import io as _io

        import mido

        if not midi_bytes:
            raise MidiComposeError("MIDI input is empty")
        if not midi_bytes.startswith(b"MThd"):
            raise MidiComposeError(
                "input does not look like a Standard MIDI File (missing 'MThd')"
            )
        try:
            mid = mido.MidiFile(file=_io.BytesIO(midi_bytes))
        except (ValueError, EOFError, IndexError, OSError) as exc:
            raise MidiComposeError(f"failed to parse MIDI: {exc}") from exc

        # Collect global meta events (tempo + time signature + key sig)
        # — they can live on any track in type-0 files but conventionally
        # are in track 0 in type-1.
        tempo_changes: list[dict[str, Any]] = []
        time_signatures: list[dict[str, Any]] = []
        key_signatures: list[dict[str, Any]] = []
        for trk in mid.tracks:
            t_ticks = 0
            for msg in trk:
                t_ticks += msg.time
                if msg.type == "set_tempo":
                    tempo_changes.append({
                        "tick": t_ticks,
                        "bpm": float(mido.tempo2bpm(msg.tempo)),
                    })
                elif msg.type == "time_signature":
                    time_signatures.append({
                        "tick": t_ticks,
                        "numerator": int(msg.numerator),
                        "denominator": int(msg.denominator),
                    })
                elif msg.type == "key_signature":
                    key_signatures.append({
                        "tick": t_ticks,
                        "key": str(msg.key),
                    })

        # Per-track stats — note counts per channel, programs used,
        # name, length in ticks + beats.
        track_summaries: list[dict[str, Any]] = []
        for tidx, trk in enumerate(mid.tracks):
            t_ticks = 0
            note_on = 0
            note_off = 0
            channels: set[int] = set()
            programs: set[int] = set()
            track_name = None
            for msg in trk:
                t_ticks += msg.time
                if msg.type == "track_name":
                    track_name = str(msg.name)
                elif msg.type == "note_on":
                    if msg.velocity > 0:
                        note_on += 1
                    else:
                        note_off += 1
                    channels.add(int(msg.channel))
                elif msg.type == "note_off":
                    note_off += 1
                    channels.add(int(msg.channel))
                elif msg.type == "program_change":
                    programs.add(int(msg.program))
                    channels.add(int(msg.channel))
            track_summaries.append({
                "index": tidx,
                "name": track_name,
                "length_ticks": t_ticks,
                "length_beats": (t_ticks / mid.ticks_per_beat) if mid.ticks_per_beat else 0.0,
                "note_on_count": note_on,
                "note_off_count": note_off,
                "channels": sorted(channels),
                "programs": sorted(programs),
            })

        return {
            "type": int(mid.type),
            "ticks_per_beat": int(mid.ticks_per_beat),
            "length_seconds": float(mid.length),
            "tempo_changes": tempo_changes,
            "time_signatures": time_signatures,
            "key_signatures": key_signatures,
            "tracks": track_summaries,
            "track_count": len(mid.tracks),
            "size_bytes": len(midi_bytes),
        }

    # ── transform: SMF bytes → modified SMF bytes ──────────────────────────

    async def transform(
        self,
        midi_bytes: bytes,
        *,
        transpose_semitones: int = 0,
        quantize_grid_beats: float | None = None,
        tempo_bpm: float | None = None,
        keep_channels: list[int] | None = None,
        drop_channels: list[int] | None = None,
    ) -> bytes:
        """Apply a sequence of transformations to a MIDI file.

        - ``transpose_semitones``: shift every note on a non-drum channel
          by N semitones (drums = channel 9, never transposed).
        - ``quantize_grid_beats``: snap every note-on event to the nearest
          multiple of this many beats (e.g. ``0.25`` = 16th-note grid).
          Note durations are preserved.
        - ``tempo_bpm``: replace every set_tempo event with this BPM.
        - ``keep_channels`` / ``drop_channels``: filter notes by MIDI
          channel. ``keep_channels`` is whitelist; ``drop_channels`` is
          blacklist; supply only one.
        """
        if keep_channels is not None and drop_channels is not None:
            raise MidiComposeError(
                "supply either keep_channels or drop_channels, not both"
            )
        if quantize_grid_beats is not None and quantize_grid_beats <= 0:
            raise MidiComposeError(
                f"quantize_grid_beats must be > 0, got {quantize_grid_beats}"
            )
        if tempo_bpm is not None and not (1.0 <= tempo_bpm <= 999.0):
            raise MidiComposeError(
                f"tempo_bpm must be in [1, 999], got {tempo_bpm}"
            )
        if not (-48 <= transpose_semitones <= 48):
            raise MidiComposeError(
                f"transpose_semitones must be in [-48, 48], got {transpose_semitones}"
            )
        async with self._lock:
            result = await asyncio.to_thread(
                self._transform_sync,
                midi_bytes,
                transpose_semitones,
                quantize_grid_beats,
                tempo_bpm,
                keep_channels,
                drop_channels,
            )
            self._touch()
            return result

    def _transform_sync(
        self,
        midi_bytes: bytes,
        transpose: int,
        quantize: float | None,
        tempo_bpm: float | None,
        keep_channels: list[int] | None,
        drop_channels: list[int] | None,
    ) -> bytes:
        import io as _io

        import mido

        if not midi_bytes:
            raise MidiComposeError("MIDI input is empty")
        if not midi_bytes.startswith(b"MThd"):
            raise MidiComposeError(
                "input does not look like a Standard MIDI File (missing 'MThd')"
            )
        try:
            mid = mido.MidiFile(file=_io.BytesIO(midi_bytes))
        except (ValueError, EOFError, IndexError, OSError) as exc:
            raise MidiComposeError(f"failed to parse MIDI: {exc}") from exc

        tpb = mid.ticks_per_beat
        new_tempo = mido.bpm2tempo(tempo_bpm) if tempo_bpm is not None else None
        keep_set = set(keep_channels) if keep_channels is not None else None
        drop_set = set(drop_channels) if drop_channels is not None else None

        def channel_allowed(ch: int) -> bool:
            if keep_set is not None:
                return ch in keep_set
            if drop_set is not None:
                return ch not in drop_set
            return True

        new_tracks: list["mido.MidiTrack"] = []
        for trk in mid.tracks:
            # Flatten to absolute ticks for easier quantisation.
            t_ticks = 0
            absolute: list[tuple[int, "mido.Message"]] = []
            for msg in trk:
                t_ticks += msg.time
                absolute.append((t_ticks, msg.copy(time=0)))

            transformed: list[tuple[int, "mido.Message"]] = []
            # Track pending note_on starts per (channel, original-pitch)
            # so quantising both ends preserves duration.
            for tick, msg in absolute:
                # Filter by channel — drop any per-channel message
                # (note events, program change, control change, etc.)
                # not just note events, so inspect doesn't see the channel at all.
                if hasattr(msg, "channel") and not channel_allowed(int(msg.channel)):
                    continue
                # Transpose (skip drums on channel 9).
                is_note = msg.type in ("note_on", "note_off")
                if is_note and int(msg.channel) != 9 and transpose != 0:
                    new_note = int(msg.note) + transpose
                    if 0 <= new_note <= 127:
                        msg = msg.copy(note=new_note)
                    else:
                        # Out-of-range note after transpose — drop it
                        # rather than wrap or clip silently.
                        continue
                # Tempo override.
                if msg.type == "set_tempo" and new_tempo is not None:
                    msg = msg.copy(tempo=new_tempo)
                # Quantise note_on times (note_off shifts by the same
                # delta so duration is preserved).
                if quantize is not None and msg.type == "note_on" and msg.velocity > 0:
                    grid_ticks = max(1, int(round(quantize * tpb)))
                    q_tick = round(tick / grid_ticks) * grid_ticks
                    delta = q_tick - tick
                    transformed.append((q_tick, msg))
                    # Find and shift the matching note_off by the same delta.
                    for i in range(len(absolute)):
                        atick, amsg = absolute[i]
                        if atick <= tick:
                            continue
                        is_off = (
                            amsg.type == "note_off"
                            or (amsg.type == "note_on" and amsg.velocity == 0)
                        )
                        if (
                            is_off
                            and int(amsg.channel) == int(msg.channel)
                            and int(amsg.note) == int(msg.note)
                        ):
                            absolute[i] = (atick + delta, amsg)
                            break
                    continue
                transformed.append((tick, msg))

            transformed.sort(key=lambda x: (x[0], 0 if x[1].type == "note_off" else 1))
            new_trk = mido.MidiTrack()
            prev = 0
            for tick, msg in transformed:
                new_trk.append(msg.copy(time=max(0, tick - prev)))
                prev = tick
            new_tracks.append(new_trk)

        out = mido.MidiFile(type=mid.type, ticks_per_beat=tpb)
        out.tracks.extend(new_tracks)
        buf = io.BytesIO()
        out.save(file=buf)
        return buf.getvalue()

    # ── drum_pattern — step-sequencer spec → GM drum MIDI ─────────────────

    async def drum_pattern(self, spec: dict) -> bytes:
        """Synthesize a MIDI drum pattern from a step-sequencer spec.

        spec = {
            "tempo_bpm": 120,         (optional, default 120)
            "steps": 16,              (optional, default 16 — steps per bar)
            "bars": 1,                (optional, default 1 — bars to generate)
            "swing": 0.0,             (optional, 0.0–0.5 swing amount)
            "pattern": {              (required)
                "kick":  [1,0,0,0,...],
                "snare": [0,0,0,0,...],
                "hihat": [1,1,1,1,...],
                ...
            }
        }
        """
        async with self._lock:
            result = await asyncio.to_thread(self._drum_pattern_sync, spec)
            self._touch()
            return result

    def _drum_pattern_sync(self, spec: dict) -> bytes:
        import mido

        if not isinstance(spec, dict):
            raise MidiComposeError("spec must be a JSON object")

        tempo_bpm = _bounded_float("tempo_bpm", spec.get("tempo_bpm", 120), 1.0, 999.0)
        steps = _bounded_int("steps", spec.get("steps", 16), 1, 64)
        bars = _bounded_int("bars", spec.get("bars", 1), 1, 64)
        swing = _bounded_float("swing", spec.get("swing", 0.0), 0.0, 0.5)

        pattern = spec.get("pattern")
        if not isinstance(pattern, dict) or not pattern:
            raise MidiComposeError("spec.pattern must be a non-empty object")

        tpb = 480
        beats_per_bar = 4
        bar_ticks = tpb * beats_per_bar
        ticks_per_step = max(1, bar_ticks // steps)

        mid = mido.MidiFile(type=1, ticks_per_beat=tpb)

        tempo_track = mido.MidiTrack()
        tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
        mid.tracks.append(tempo_track)

        drum_track = mido.MidiTrack()
        drum_track.append(mido.MetaMessage("track_name", name="Drums", time=0))
        drum_track.append(mido.Message("program_change", channel=9, program=0, time=0))

        channel = 9
        events: list[tuple[int, "mido.Message"]] = []

        for instrument, steps_list in pattern.items():
            if not isinstance(steps_list, list):
                raise MidiComposeError(f"pattern.{instrument} must be a list")

            note_key = instrument.lower()
            if note_key in _DRUM_NOTE_MAP:
                note = _DRUM_NOTE_MAP[note_key]
            else:
                try:
                    note = int(instrument)
                    if not (0 <= note <= 127):
                        raise MidiComposeError(
                            f"pattern key {instrument!r}: note must be 0–127"
                        )
                except (ValueError, TypeError) as exc:
                    raise MidiComposeError(
                        f"unknown drum instrument {instrument!r}; "
                        f"supported: {sorted(_DRUM_NOTE_MAP.keys())}"
                    ) from exc

            for bar_idx in range(bars):
                for step_idx, hit in enumerate(steps_list):
                    if not hit:
                        continue
                    velocity = int(min(127, max(1, hit if isinstance(hit, int) and hit > 1 else 100)))
                    tick = bar_ticks * bar_idx + step_idx * ticks_per_step
                    if swing > 0 and step_idx % 2 == 1:
                        tick += int(swing * ticks_per_step * 2)
                    off_tick = tick + max(1, ticks_per_step // 2)
                    events.append((tick, mido.Message(
                        "note_on", channel=channel, note=note, velocity=velocity, time=0,
                    )))
                    events.append((off_tick, mido.Message(
                        "note_off", channel=channel, note=note, velocity=0, time=0,
                    )))

        events.sort(key=lambda x: (x[0], 0 if x[1].type == "note_off" else 1))
        prev = 0
        for tick, msg in events:
            msg.time = tick - prev
            drum_track.append(msg)
            prev = tick

        mid.tracks.append(drum_track)
        buf = io.BytesIO()
        mid.save(file=buf)
        return buf.getvalue()
