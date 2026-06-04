"""librosa MIR analysis + pyloudnorm LUFS engine (librosa 0.10.2, ISC).

Features:
  bpm              — beat tracking via ``librosa.beat.beat_track``
  key              — Krumhansl-Schmuckler key estimation against the chroma vector
  loudness         — integrated LUFS via ``pyloudnorm`` (ITU-R BS.1770-4)
  duration         — file duration in seconds (always returned)
  spectral_centroid — mean spectral centroid in Hz
  rms              — root mean square energy (mean across frames)
  zcr              — mean zero-crossing rate

Also provides ``measure_lufs()`` and ``normalize_lufs()`` for the
``/v1/audio/loudness`` endpoint. No model weights — ``get_model()`` is a
no-op.

`librosa.beat.beat_track` returns numpy floats; we cast to native ``float``
before returning so the FastAPI JSON encoder doesn't trip on numpy types.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

from ..audio import AudioConversionError, encode_audio, to_wav_float32
from .base import EngineBase

# Krumhansl-Schmuckler reference profiles (major + minor). Indexed by pitch
# class 0..11 (C..B). The chroma vector of the input is correlated against
# all 24 rotations of these profiles; argmax → key.
_KS_MAJOR = (6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88)
_KS_MINOR = (6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17)
_PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


class LibrosaAnalyzeEngine(EngineBase):
    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)

    async def analyze(
        self,
        raw: bytes,
        filename: str,
        features: list[str],
    ) -> dict[str, Any]:
        async with self._lock:
            result = await asyncio.to_thread(
                self._analyze_sync, raw, filename, features
            )
            self._touch()
            return result

    def _analyze_sync(
        self, raw: bytes, filename: str, features: list[str]
    ) -> dict[str, Any]:
        import librosa
        import numpy as np

        wav_path = to_wav_float32(raw, filename)
        try:
            # mono signal for BPM / chroma / spectral; LUFS uses stereo.
            y_mono, sr = librosa.load(wav_path, sr=None, mono=True)
            out: dict[str, Any] = {"duration": float(len(y_mono) / sr)}

            wanted = set(features) if features else {
                "bpm", "key", "loudness", "duration",
                "spectral_centroid", "rms", "zcr",
            }

            if "bpm" in wanted:
                try:
                    tempo, _ = librosa.beat.beat_track(y=y_mono, sr=sr)
                    out["bpm"] = float(np.atleast_1d(tempo)[0])
                except Exception as exc:  # noqa: BLE001
                    self._log.warning("bpm feature failed: %s", exc)
                    out["bpm"] = None

            if "key" in wanted:
                try:
                    chroma = librosa.feature.chroma_cqt(y=y_mono, sr=sr)
                    out["key"] = _estimate_key(np.asarray(chroma))
                except Exception as exc:  # noqa: BLE001
                    self._log.warning("key feature failed: %s", exc)
                    out["key"] = None

            if "loudness" in wanted:
                try:
                    out["loudness_lufs"] = _lufs_from_wav(wav_path)
                except Exception as exc:  # noqa: BLE001
                    self._log.warning("loudness feature failed: %s", exc)
                    out["loudness_lufs"] = None

            if "spectral_centroid" in wanted:
                try:
                    sc = librosa.feature.spectral_centroid(y=y_mono, sr=sr)
                    out["spectral_centroid"] = float(np.mean(sc))
                except Exception as exc:  # noqa: BLE001
                    self._log.warning("spectral_centroid feature failed: %s", exc)
                    out["spectral_centroid"] = None

            if "rms" in wanted:
                try:
                    rms = librosa.feature.rms(y=y_mono)
                    out["rms"] = float(np.mean(rms))
                except Exception as exc:  # noqa: BLE001
                    self._log.warning("rms feature failed: %s", exc)
                    out["rms"] = None

            if "zcr" in wanted:
                try:
                    zcr = librosa.feature.zero_crossing_rate(y_mono)
                    out["zcr"] = float(np.mean(zcr))
                except Exception as exc:  # noqa: BLE001
                    self._log.warning("zcr feature failed: %s", exc)
                    out["zcr"] = None

            return out
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    async def measure_lufs(self, raw: bytes, filename: str) -> float:
        async with self._lock:
            result = await asyncio.to_thread(self._measure_sync, raw, filename)
            self._touch()
            return result

    def _measure_sync(self, raw: bytes, filename: str) -> float:
        wav_path = to_wav_float32(raw, filename)
        try:
            return _lufs_from_wav(wav_path)
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    async def normalize_lufs(
        self,
        raw: bytes,
        filename: str,
        *,
        target_lufs: float,
        output_format: str = "wav",
    ) -> tuple[bytes, float]:
        async with self._lock:
            result = await asyncio.to_thread(
                self._normalize_sync, raw, filename, target_lufs, output_format
            )
            self._touch()
            return result

    # ── beats ──────────────────────────────────────────────────────────────

    async def beats(
        self,
        raw: bytes,
        filename: str,
        *,
        click_track: bool = False,
        output_format: str = "wav",
        start_bpm: float | None = None,
    ) -> dict[str, Any]:
        """Full beat tracking — returns BPM + per-beat times. With
        ``click_track=True``, also returns a base64-encoded audio rendering
        of the input mixed with a metronome click on each beat."""
        async with self._lock:
            result = await asyncio.to_thread(
                self._beats_sync, raw, filename, click_track, output_format, start_bpm,
            )
            self._touch()
            return result

    def _beats_sync(
        self,
        raw: bytes,
        filename: str,
        click_track: bool,
        output_format: str,
        start_bpm: float | None,
    ) -> dict[str, Any]:
        import base64

        import librosa
        import numpy as np
        import soundfile as sf

        wav_path = to_wav_float32(raw, filename)
        try:
            y, sr = librosa.load(wav_path, sr=None, mono=True)
            kw = {"start_bpm": start_bpm} if start_bpm is not None else {}
            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr, **kw)
            tempo_val = float(np.atleast_1d(tempo)[0])
            beat_times = librosa.frames_to_time(beat_frames, sr=sr).tolist()
            result: dict[str, Any] = {
                "tempo_bpm": tempo_val,
                "beats": [float(t) for t in beat_times],
                "beat_count": len(beat_times),
                "duration": float(len(y) / sr),
            }
            if not click_track:
                return result

            # Mix librosa's synthesized click with the original at -6 dB
            # so the input is still audible underneath. librosa.clicks
            # returns the click pattern at the same sample rate.
            clicks = librosa.clicks(
                frames=beat_frames, sr=sr, length=len(y),
            )
            mixed = (y * 0.5) + (clicks * 0.5)
            np.clip(mixed, -1.0, 1.0, out=mixed)

            out_fd, out_wav = tempfile.mkstemp(prefix="audiolla-click-", suffix=".wav")
            os.close(out_fd)
            try:
                sf.write(out_wav, mixed, sr, subtype="PCM_16")
                audio_bytes, _ct = encode_audio(out_wav, output_format)
            finally:
                try:
                    os.unlink(out_wav)
                except OSError:
                    pass
            result["click_track_base64"] = base64.b64encode(audio_bytes).decode("ascii")
            result["output_format"] = output_format
            return result
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    # ── onsets ─────────────────────────────────────────────────────────────

    async def onsets(self, raw: bytes, filename: str) -> dict[str, Any]:
        """Onset (transient) detection — returns time + relative strength
        for each detected attack. Useful for sample slicing, drum hit
        detection, and rhythm analysis."""
        async with self._lock:
            result = await asyncio.to_thread(self._onsets_sync, raw, filename)
            self._touch()
            return result

    def _onsets_sync(self, raw: bytes, filename: str) -> dict[str, Any]:
        import librosa
        import numpy as np

        wav_path = to_wav_float32(raw, filename)
        try:
            y, sr = librosa.load(wav_path, sr=None, mono=True)
            onset_env = librosa.onset.onset_strength(y=y, sr=sr)
            onset_frames = librosa.onset.onset_detect(
                onset_envelope=onset_env, sr=sr,
            )
            onset_times = librosa.frames_to_time(onset_frames, sr=sr)
            # Strength at each onset frame, normalised to [0, 1] for
            # easier downstream filtering ("strong onsets only").
            if len(onset_env) > 0:
                env_max = float(np.max(onset_env)) or 1.0
                strengths = (onset_env[onset_frames] / env_max).tolist()
            else:
                strengths = []
            return {
                "onsets": [
                    {"time": float(t), "strength": float(s)}
                    for t, s in zip(onset_times.tolist(), strengths)
                ],
                "count": int(len(onset_frames)),
                "duration": float(len(y) / sr),
            }
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    # ── melody (pyin pitch contour) ────────────────────────────────────────

    async def melody(
        self,
        raw: bytes,
        filename: str,
        *,
        fmin: float = 65.0,    # C2 — typical vocal/instrument low
        fmax: float = 2093.0,  # C7 — typical vocal/instrument high
        as_midi: bool = False,
    ) -> dict[str, Any]:
        """Monophonic pitch tracking via pYIN. Returns a contour of
        ``(time, hz, voiced)`` triples by default. With ``as_midi=True``,
        also quantises the voiced segments into MIDI notes (note_on
        when pitch becomes voiced, note_off when it goes unvoiced or
        the rounded MIDI note changes) and returns base64 MIDI."""
        async with self._lock:
            result = await asyncio.to_thread(
                self._melody_sync, raw, filename, fmin, fmax, as_midi,
            )
            self._touch()
            return result

    def _melody_sync(
        self,
        raw: bytes,
        filename: str,
        fmin: float,
        fmax: float,
        as_midi: bool,
    ) -> dict[str, Any]:
        import base64
        import io

        import librosa
        import mido
        import numpy as np

        if fmin >= fmax:
            raise AudioConversionError(
                f"fmin ({fmin}) must be less than fmax ({fmax})"
            )

        wav_path = to_wav_float32(raw, filename)
        try:
            y, sr = librosa.load(wav_path, sr=None, mono=True)
            f0, voiced_flag, voiced_prob = librosa.pyin(
                y, fmin=fmin, fmax=fmax, sr=sr,
            )
            times = librosa.times_like(f0, sr=sr)
            # Replace NaNs (unvoiced frames) with None so the JSON is
            # cleanly serialisable. Typed Any so mypy doesn't infer the
            # narrowest common value type across the heterogeneous dict.
            contour: list[dict[str, Any]] = []
            for t, hz, v in zip(times.tolist(), f0.tolist(), voiced_flag.tolist()):
                contour.append({
                    "time": float(t),
                    "hz": (float(hz) if (hz is not None and not np.isnan(hz)) else None),
                    "voiced": bool(v),
                })

            result: dict[str, Any] = {
                "fmin": fmin,
                "fmax": fmax,
                "frame_seconds": float(times[1] - times[0]) if len(times) > 1 else None,
                "contour": contour,
                "duration": float(len(y) / sr),
            }

            if not as_midi:
                return result

            # Quantise to MIDI notes — emit a note for each contiguous
            # voiced run with the same rounded MIDI pitch.
            midi_notes: list[dict[str, Any]] = []
            cur_pitch: int | None = None
            cur_start: float = 0.0
            for entry in contour:
                entry_time = float(entry["time"])  # always finite; only hz can be None
                entry_hz = entry["hz"]
                if not entry["voiced"] or entry_hz is None:
                    if cur_pitch is not None:
                        midi_notes.append({
                            "pitch": cur_pitch,
                            "start_sec": cur_start,
                            "end_sec": entry_time,
                        })
                        cur_pitch = None
                    continue
                p = int(round(librosa.hz_to_midi(entry_hz)))
                if cur_pitch is None:
                    cur_pitch = p
                    cur_start = entry_time
                elif p != cur_pitch:
                    midi_notes.append({
                        "pitch": cur_pitch,
                        "start_sec": cur_start,
                        "end_sec": entry_time,
                    })
                    cur_pitch = p
                    cur_start = entry_time
            # Flush trailing note.
            if cur_pitch is not None and len(contour) > 0:
                midi_notes.append({
                    "pitch": cur_pitch,
                    "start_sec": cur_start,
                    "end_sec": contour[-1]["time"],
                })
            # Filter out sub-30 ms blips — usually pyin noise.
            midi_notes = [n for n in midi_notes if n["end_sec"] - n["start_sec"] >= 0.03]

            # Serialise to a 1-track MIDI at 120 BPM (caller can
            # re-tempo via /v1/midi/transform).
            tpq = 480
            bpm = 120.0
            seconds_per_tick = 60.0 / bpm / tpq
            mid = mido.MidiFile(type=1, ticks_per_beat=tpq)
            tempo_track = mido.MidiTrack()
            tempo_track.append(mido.MetaMessage(
                "set_tempo", tempo=mido.bpm2tempo(bpm), time=0,
            ))
            mid.tracks.append(tempo_track)
            mel_track = mido.MidiTrack()
            mel_track.append(mido.Message("program_change", channel=0, program=0, time=0))
            events: list[tuple[int, "mido.Message"]] = []
            for n in midi_notes:
                on_tick = int(round(n["start_sec"] / seconds_per_tick))
                off_tick = int(round(n["end_sec"] / seconds_per_tick))
                if off_tick <= on_tick:
                    off_tick = on_tick + 1
                events.append((on_tick, mido.Message(
                    "note_on", channel=0, note=n["pitch"], velocity=100, time=0,
                )))
                events.append((off_tick, mido.Message(
                    "note_off", channel=0, note=n["pitch"], velocity=0, time=0,
                )))
            events.sort(key=lambda x: (x[0], 0 if x[1].type == "note_off" else 1))
            prev = 0
            for tick, msg in events:
                msg.time = tick - prev
                mel_track.append(msg)
                prev = tick
            mid.tracks.append(mel_track)

            buf = io.BytesIO()
            mid.save(file=buf)
            midi_bytes = buf.getvalue()
            result["midi_base64"] = base64.b64encode(midi_bytes).decode("ascii")
            result["midi_size"] = len(midi_bytes)
            result["midi_notes"] = midi_notes
            return result
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    # ── segments (music structure) ─────────────────────────────────────────

    async def segments(
        self,
        raw: bytes,
        filename: str,
        *,
        num_segments: int = 6,
    ) -> dict[str, Any]:
        """Music structure segmentation via spectral clustering of the
        recurrence matrix. Returns ``num_segments`` non-overlapping ranges
        labelled A/B/C/... by cluster, so structurally similar regions
        share a label (good for spotting verse/chorus repetition)."""
        async with self._lock:
            result = await asyncio.to_thread(
                self._segments_sync, raw, filename, num_segments,
            )
            self._touch()
            return result

    def _segments_sync(
        self,
        raw: bytes,
        filename: str,
        num_segments: int,
    ) -> dict[str, Any]:
        import librosa
        import numpy as np

        if num_segments < 2 or num_segments > 32:
            raise AudioConversionError(
                f"num_segments must be in [2, 32], got {num_segments}"
            )

        wav_path = to_wav_float32(raw, filename)
        try:
            y, sr = librosa.load(wav_path, sr=None, mono=True)
            # Mel spectrogram + log scaling, beat-synchronous summary —
            # this matches the librosa "Laplacian segmentation" tutorial.
            BINS_PER_OCTAVE = 12 * 3
            N_OCTAVES = 7
            cqt = np.abs(librosa.cqt(
                y=y, sr=sr,
                bins_per_octave=BINS_PER_OCTAVE,
                n_bins=N_OCTAVES * BINS_PER_OCTAVE,
            ))
            C = librosa.amplitude_to_db(cqt, ref=np.max)
            tempo, beats = librosa.beat.beat_track(y=y, sr=sr, trim=False)
            # Need enough beats to build a meaningful recurrence matrix —
            # recurrence_matrix needs at least width+1 frames after sync.
            min_beats = max(num_segments, 6)
            if len(beats) < min_beats:
                # Short or featureless input — return one undifferentiated
                # "A" segment spanning the whole file rather than crash.
                return {
                    "segments": [{
                        "start_sec": 0.0,
                        "end_sec": float(len(y) / sr),
                        "label": "A",
                        "cluster_id": 0,
                    }],
                    "tempo_bpm": float(np.atleast_1d(tempo)[0]),
                    "duration": float(len(y) / sr),
                    "note": (
                        f"input too short for {num_segments}-segment "
                        f"clustering (only {len(beats)} beats detected); "
                        "returning a single span"
                    ),
                }
            Csync = librosa.util.sync(C, beats, aggregate=np.median)
            R = librosa.segment.recurrence_matrix(
                Csync, width=3, mode="affinity", sym=True,
            )
            seg_ids = librosa.segment.agglomerative(R, num_segments)
            beat_times = librosa.frames_to_time(beats, sr=sr)
            # Group consecutive beats with the same cluster id into ranges.
            ranges: list[dict[str, Any]] = []
            if len(seg_ids) == 0:
                return {"segments": [], "duration": float(len(y) / sr)}
            cur_label = int(seg_ids[0])
            cur_start = float(beat_times[0]) if len(beat_times) > 0 else 0.0
            for i in range(1, len(seg_ids)):
                if int(seg_ids[i]) != cur_label:
                    end = float(beat_times[i])
                    ranges.append({
                        "start_sec": cur_start,
                        "end_sec": end,
                        "label": chr(ord("A") + cur_label % 26),
                        "cluster_id": cur_label,
                    })
                    cur_label = int(seg_ids[i])
                    cur_start = end
            # Trailing range to end of audio.
            ranges.append({
                "start_sec": cur_start,
                "end_sec": float(len(y) / sr),
                "label": chr(ord("A") + cur_label % 26),
                "cluster_id": cur_label,
            })
            return {
                "segments": ranges,
                "tempo_bpm": float(np.atleast_1d(tempo)[0]),
                "duration": float(len(y) / sr),
            }
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    def _normalize_sync(
        self,
        raw: bytes,
        filename: str,
        target_lufs: float,
        output_format: str,
    ) -> tuple[bytes, float]:
        import numpy as np
        import pyloudnorm as pyln
        import soundfile as sf

        wav_path = to_wav_float32(raw, filename)
        out_fd, out_wav = tempfile.mkstemp(prefix="audiolla-norm-", suffix=".wav")
        os.close(out_fd)
        try:
            audio, sr = sf.read(wav_path, always_2d=False, dtype="float32")
            meter = pyln.Meter(sr)
            measured = float(meter.integrated_loudness(audio))
            if not np.isfinite(measured):
                # Silent or near-silent input — pyln.normalize.loudness would
                # multiply by ~10**inf, np.clip then produces a brick-wall
                # full-scale output. Refuse loudly instead.
                raise AudioConversionError(
                    "audio is too quiet or silent to normalize "
                    f"(measured LUFS is not finite: {measured})"
                )
            normalized = pyln.normalize.loudness(audio, measured, target_lufs)
            np.clip(normalized, -1.0, 1.0, out=normalized)
            sf.write(out_wav, normalized, sr, subtype="PCM_16")
            audio_bytes, _ct = encode_audio(out_wav, output_format)
            return audio_bytes, measured
        finally:
            for p in (wav_path, out_wav):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    # ── loudness_curve ─────────────────────────────────────────────────────

    async def loudness_curve_method(
        self,
        raw: bytes,
        filename: str,
        *,
        hop_length: int = 512,
    ) -> dict:
        """RMS envelope as loudness curve over time."""
        async with self._lock:
            from ..audio import loudness_curve  # noqa: PLC0415
            result = await asyncio.to_thread(loudness_curve, raw, filename, hop_length=hop_length)
            self._touch()
            return result

    # ── pitch_correct ──────────────────────────────────────────────────────

    async def pitch_correct(
        self,
        raw: bytes,
        filename: str,
        *,
        strength: float = 1.0,
        output_format: str = "wav",
    ) -> bytes:
        """Pitch-correct audio toward nearest chromatic semitone.

        Uses pyin F0 detection to find the dominant pitch offset, then
        applies librosa pitch_shift to move toward the nearest semitone.
        strength=1.0 is full correction, 0.0 is dry pass-through.
        """
        async with self._lock:
            result = await asyncio.to_thread(
                self._pitch_correct_sync, raw, filename, strength, output_format,
            )
            self._touch()
            return result

    def _pitch_correct_sync(
        self,
        raw: bytes,
        filename: str,
        strength: float,
        output_format: str,
    ) -> bytes:
        import librosa
        import numpy as np
        import soundfile as sf

        from ..audio import SUPPORTED_OUTPUT_FORMATS  # noqa: PLC0415

        if not (0.0 <= strength <= 1.0):
            raise AudioConversionError(
                f"strength must be in [0.0, 1.0], got {strength}"
            )
        if output_format not in SUPPORTED_OUTPUT_FORMATS:
            raise AudioConversionError(
                f"unsupported output format {output_format!r}; "
                f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
            )

        wav_path = to_wav_float32(raw, filename)
        out_wav_path = None
        try:
            y, sr = librosa.load(wav_path, sr=None, mono=False)
            y_mono = librosa.to_mono(y) if y.ndim > 1 else y

            f0, voiced_flag, _ = librosa.pyin(
                y_mono,
                fmin=float(librosa.note_to_hz("C2")),
                fmax=float(librosa.note_to_hz("C7")),
                sr=sr,
            )
            voiced_f0 = f0[voiced_flag & np.isfinite(f0)]

            if len(voiced_f0) < 4 or strength < 0.001:
                out_bytes, _ = encode_audio(wav_path, output_format)
                return out_bytes

            median_hz = float(np.median(voiced_f0))
            median_midi = float(librosa.hz_to_midi(median_hz))
            nearest_midi = round(median_midi)
            full_shift = float(nearest_midi - median_midi)

            if abs(full_shift) < 0.05:
                out_bytes, _ = encode_audio(wav_path, output_format)
                return out_bytes

            if y.ndim > 1:
                shifted = np.stack([
                    librosa.effects.pitch_shift(y[i], sr=sr, n_steps=full_shift)
                    for i in range(y.shape[0])
                ], axis=0)
            else:
                shifted = librosa.effects.pitch_shift(y, sr=sr, n_steps=full_shift)

            result = shifted * strength + y * (1.0 - strength)
            np.clip(result, -1.0, 1.0, out=result)

            out_wav_fd, out_wav_path = tempfile.mkstemp(
                prefix="audiolla-pc-out-", suffix=".wav"
            )
            os.close(out_wav_fd)
            if result.ndim > 1:
                sf.write(out_wav_path, result.T, sr, subtype="FLOAT")
            else:
                sf.write(out_wav_path, result, sr, subtype="FLOAT")
            out_bytes, _ = encode_audio(out_wav_path, output_format)
            return out_bytes
        finally:
            for p in filter(None, [wav_path, out_wav_path]):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    # ── loop_point ─────────────────────────────────────────────────────────

    async def loop_point(
        self,
        raw: bytes,
        filename: str,
        *,
        min_loop_bars: int = 4,
        num_candidates: int = 5,
    ) -> dict:
        """Find the best seamless loop boundary in audio.

        Quantizes to beat grid, computes MFCC spectral similarity between
        loop start and end points, returns the highest-scoring candidate.
        """
        async with self._lock:
            result = await asyncio.to_thread(
                self._loop_point_sync, raw, filename, min_loop_bars, num_candidates,
            )
            self._touch()
            return result

    def _loop_point_sync(
        self,
        raw: bytes,
        filename: str,
        min_loop_bars: int,
        num_candidates: int,
    ) -> dict:
        import librosa
        import numpy as np

        if min_loop_bars < 1 or min_loop_bars > 64:
            raise AudioConversionError(
                f"min_loop_bars must be in [1, 64], got {min_loop_bars}"
            )

        wav_path = to_wav_float32(raw, filename)
        try:
            y, sr = librosa.load(wav_path, sr=None, mono=True)
            duration = float(len(y) / sr)

            tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
            tempo_val = float(np.atleast_1d(tempo)[0])
            beat_times = librosa.frames_to_time(beat_frames, sr=sr)

            min_beats_needed = min_loop_bars * 4 + 2
            if len(beat_times) < min_beats_needed:
                return {
                    "loop_start_sec": round(float(beat_times[0]) if len(beat_times) > 0 else 0.0, 4),
                    "loop_end_sec": round(duration, 4),
                    "bars": 0,
                    "score": 0.0,
                    "tempo_bpm": round(tempo_val, 2),
                    "duration": round(duration, 4),
                    "candidates": [],
                    "note": (
                        f"too few beats for {min_loop_bars}-bar loop analysis "
                        f"(found {len(beat_times)}, need {min_beats_needed})"
                    ),
                }

            hop = 512
            mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=hop)

            def feat_at(t: float) -> "np.ndarray":
                w = max(1, int(librosa.time_to_frames(
                    2 * 60.0 / max(tempo_val, 1.0), sr=sr, hop_length=hop
                )))
                frame = librosa.time_to_frames(t, sr=sr, hop_length=hop)
                s = max(0, frame - w // 2)
                e = min(mfcc.shape[1], frame + w // 2)
                if e <= s:
                    return np.zeros(13)
                return np.mean(mfcc[:, s:e], axis=1)

            beats_per_bar = 4
            seen: set[tuple[float, float]] = set()
            candidates: list[tuple[float, float, float, int]] = []

            for bar_count in range(min_loop_bars, len(beat_times) // beats_per_bar + 1):
                loop_beats = bar_count * beats_per_bar
                if loop_beats >= len(beat_times):
                    break
                for start_idx in range(0, len(beat_times) - loop_beats, beats_per_bar):
                    end_idx = start_idx + loop_beats
                    if end_idx >= len(beat_times):
                        break
                    start_t = float(beat_times[start_idx])
                    end_t = float(beat_times[end_idx])
                    key = (round(start_t, 3), round(end_t, 3))
                    if key in seen:
                        continue
                    seen.add(key)
                    fs = feat_at(start_t)
                    fe = feat_at(end_t)
                    ns, ne = float(np.linalg.norm(fs)), float(np.linalg.norm(fe))
                    score = float(np.dot(fs, fe) / (ns * ne)) if ns > 0 and ne > 0 else 0.0
                    candidates.append((score, start_t, end_t, bar_count))
                    if len(candidates) >= num_candidates * 20:
                        break
                if len(candidates) >= num_candidates * 20:
                    break

            if not candidates:
                return {
                    "loop_start_sec": round(float(beat_times[0]), 4),
                    "loop_end_sec": round(float(beat_times[min(min_loop_bars * 4, len(beat_times) - 1)]), 4),
                    "bars": min_loop_bars,
                    "score": 0.0,
                    "tempo_bpm": round(tempo_val, 2),
                    "duration": round(duration, 4),
                    "candidates": [],
                }

            candidates.sort(key=lambda x: -x[0])
            best_score, best_start, best_end, best_bars = candidates[0]
            top = [
                {
                    "start_sec": round(s, 4),
                    "end_sec": round(e, 4),
                    "bars": b,
                    "score": round(sc, 4),
                }
                for sc, s, e, b in candidates[:num_candidates]
            ]
            return {
                "loop_start_sec": round(best_start, 4),
                "loop_end_sec": round(best_end, 4),
                "bars": best_bars,
                "score": round(best_score, 4),
                "tempo_bpm": round(tempo_val, 2),
                "duration": round(duration, 4),
                "candidates": top,
            }
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass


def _lufs_from_wav(wav_path: str) -> float:
    import pyloudnorm as pyln
    import soundfile as sf

    audio, sr = sf.read(wav_path, always_2d=False, dtype="float32")
    meter = pyln.Meter(sr)
    return float(meter.integrated_loudness(audio))


def _estimate_key(chroma: Any) -> str:
    """Krumhansl-Schmuckler key estimation.

    chroma : (12, n_frames) ndarray. We average across time, correlate the
    mean profile with rotations of the major + minor Krumhansl-Schmuckler
    reference profiles, and return the highest-correlating key as a
    UI-friendly string (e.g. "C major", "A minor").
    """
    import numpy as np

    profile = np.mean(chroma, axis=1)
    if np.linalg.norm(profile) == 0:
        return "unknown"
    profile = profile / np.linalg.norm(profile)

    maj = np.asarray(_KS_MAJOR) / np.linalg.norm(_KS_MAJOR)
    minr = np.asarray(_KS_MINOR) / np.linalg.norm(_KS_MINOR)

    best_corr = -2.0
    best_idx = 0
    best_mode = "major"
    for shift in range(12):
        rotated_maj = np.roll(maj, shift)
        rotated_min = np.roll(minr, shift)
        cmaj = float(np.dot(profile, rotated_maj))
        cmin = float(np.dot(profile, rotated_min))
        if cmaj > best_corr:
            best_corr = cmaj
            best_idx = shift
            best_mode = "major"
        if cmin > best_corr:
            best_corr = cmin
            best_idx = shift
            best_mode = "minor"
    return f"{_PITCH_CLASSES[best_idx]} {best_mode}"
