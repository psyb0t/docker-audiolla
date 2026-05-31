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
