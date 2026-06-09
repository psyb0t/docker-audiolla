"""Spectral noise reduction via noisereduce (3.x).

Stationary mode: assumes the noise profile is constant (e.g. room hum,
tape hiss). Non-stationary mode: adapts the noise estimate over time,
better for variable backgrounds. Both modes operate in the frequency
domain — no neural model, no GPU required.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time

from ..audio import AudioConversionError, encode_audio, to_wav_float32
from .base import EngineBase


class NoiseReduceEngine(EngineBase):
    async def reduce(
        self,
        raw: bytes,
        filename: str,
        *,
        stationary: bool = False,
        prop_decrease: float = 1.0,
        output_format: str = "wav",
    ) -> bytes:
        self._log.info(
            "reduce start: filename=%s input_bytes=%d stationary=%s "
            "prop_decrease=%.3f output_format=%s",
            filename, len(raw), stationary, prop_decrease, output_format,
        )
        t0 = time.perf_counter()
        async with self._lock:
            result = await asyncio.to_thread(
                self._reduce_sync, raw, filename, stationary, prop_decrease, output_format
            )
            self._touch()
            self._log.info(
                "reduce done: filename=%s duration_ms=%.1f output_bytes=%d",
                filename, (time.perf_counter() - t0) * 1000.0, len(result),
            )
            return result

    def _reduce_sync(
        self,
        raw: bytes,
        filename: str,
        stationary: bool,
        prop_decrease: float,
        output_format: str,
    ) -> bytes:
        import librosa
        import noisereduce as nr
        import soundfile as sf

        wav_path = to_wav_float32(raw, filename)
        try:
            y, sr = librosa.load(wav_path, sr=None, mono=False)
            reduced = nr.reduce_noise(
                y=y,
                sr=sr,
                stationary=stationary,
                prop_decrease=prop_decrease,
            )

            fd, tmp = tempfile.mkstemp(prefix="audiolla-nr-", suffix=".wav")
            os.close(fd)
            try:
                if reduced.ndim == 1:
                    sf.write(tmp, reduced, sr, subtype="PCM_16")
                else:
                    sf.write(tmp, reduced.T, sr, subtype="PCM_16")
                audio_bytes, _ = encode_audio(tmp, output_format)
            finally:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
            return audio_bytes

        except AudioConversionError:
            raise
        except Exception as exc:
            self._log.exception("noise reduction failed for %s", filename)
            raise AudioConversionError(f"noise reduction failed: {exc}") from exc
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass
