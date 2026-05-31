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
