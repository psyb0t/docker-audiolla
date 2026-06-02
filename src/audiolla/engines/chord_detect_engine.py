"""Chord and key detection engine via librosa chroma analysis.

Uses the Krumhansl-Schmuckler key-finding algorithm and template matching
for frame-level chord detection, then segments consecutive identical chord
labels into time-stamped regions.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

from ..audio import AudioConversionError, to_wav_float32
from .base import EngineBase


class ChordDetectError(AudioConversionError):
    """Chord/key detection failed."""


_NOTES = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]

_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


class ChordDetectEngine(EngineBase):
    def _load_sync(self) -> object:
        import librosa  # noqa: PLC0415
        import numpy as np  # noqa: PLC0415

        self._librosa = librosa
        self._np = np
        self._log.info("ChordDetectEngine ready (librosa %s)", librosa.__version__)
        return librosa

    async def detect_chords(
        self,
        raw: bytes,
        filename: str,
        *,
        hop_length: int = 512,
        segment_min_duration_sec: float = 0.5,
    ) -> dict:
        await self.get_model()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._detect_chords_sync,
            raw,
            filename,
            hop_length,
            segment_min_duration_sec,
        )
        self._touch()
        return result

    def _detect_chords_sync(
        self,
        raw: bytes,
        filename: str,
        hop_length: int,
        segment_min_duration_sec: float,
    ) -> dict:
        librosa = self._librosa
        np = self._np

        wav_path: str | None = None
        try:
            wav_path = to_wav_float32(raw, filename)
            y, sr = librosa.load(wav_path, sr=None, mono=True)

            chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=hop_length)
            chroma_mean = chroma.mean(axis=1)

            major_prof = np.array(_MAJOR_PROFILE)
            minor_prof = np.array(_MINOR_PROFILE)

            best_corr = -np.inf
            best_key = "C major"
            for root in range(12):
                maj_corr = float(np.corrcoef(chroma_mean, np.roll(major_prof, root))[0, 1])
                if maj_corr > best_corr:
                    best_corr = maj_corr
                    best_key = f"{_NOTES[root]} major"
                min_corr = float(np.corrcoef(chroma_mean, np.roll(minor_prof, root))[0, 1])
                if min_corr > best_corr:
                    best_corr = min_corr
                    best_key = f"{_NOTES[root]} minor"

            key_confidence = float(np.clip(best_corr, 0.0, 1.0))

            templates: list[tuple[str, Any]] = []
            for root in range(12):
                vec = np.zeros(12)
                vec[root % 12] = 1.0
                vec[(root + 4) % 12] = 1.0
                vec[(root + 7) % 12] = 1.0
                templates.append((f"{_NOTES[root]} major", vec))
            for root in range(12):
                vec = np.zeros(12)
                vec[root % 12] = 1.0
                vec[(root + 3) % 12] = 1.0
                vec[(root + 7) % 12] = 1.0
                templates.append((f"{_NOTES[root]} minor", vec))

            n_frames = chroma.shape[1]
            frame_labels: list[str] = []
            frame_confidences: list[float] = []
            for i in range(n_frames):
                frame = chroma[:, i]
                best_score = -np.inf
                best_label = templates[0][0]
                for label, tmpl in templates:
                    score = float(np.dot(frame, tmpl))
                    if score > best_score:
                        best_score = score
                        best_label = label
                frame_labels.append(best_label)
                frame_confidences.append(max(0.0, best_score))

            frame_times = librosa.frames_to_time(
                np.arange(n_frames), sr=sr, hop_length=hop_length
            )
            duration = float(len(y) / sr)

            raw_segments: list[dict] = []
            if n_frames > 0:
                seg_label = frame_labels[0]
                seg_start = float(frame_times[0])
                seg_confs: list[float] = [frame_confidences[0]]
                for i in range(1, n_frames):
                    if frame_labels[i] != seg_label:
                        raw_segments.append({
                            "chord": seg_label,
                            "start_sec": seg_start,
                            "end_sec": float(frame_times[i]),
                            "confidence": float(np.mean(seg_confs)),
                        })
                        seg_label = frame_labels[i]
                        seg_start = float(frame_times[i])
                        seg_confs = [frame_confidences[i]]
                    else:
                        seg_confs.append(frame_confidences[i])
                raw_segments.append({
                    "chord": seg_label,
                    "start_sec": seg_start,
                    "end_sec": duration,
                    "confidence": float(np.mean(seg_confs)),
                })

            merged: list[dict] = []
            for seg in raw_segments:
                seg_dur = seg["end_sec"] - seg["start_sec"]
                if seg_dur < segment_min_duration_sec and merged:
                    merged[-1]["end_sec"] = seg["end_sec"]
                    merged[-1]["confidence"] = (merged[-1]["confidence"] + seg["confidence"]) / 2.0
                else:
                    merged.append(dict(seg))

            return {
                "key": best_key,
                "key_confidence": key_confidence,
                "chords": merged,
                "duration": duration,
            }
        except AudioConversionError:
            raise
        except Exception as exc:
            raise ChordDetectError(f"chord detection failed: {exc}") from exc
        finally:
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)
