"""Harmonic/Percussive Source Separation via librosa HPSS median filter.

Returns two audio files: harmonic (tonal content) and percussive (transients).
No model weights — pure DSP via librosa.effects.hpss.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
import time

from ..audio import AudioConversionError, encode_audio, to_wav_float32
from .base import EngineBase


class HpssEngine(EngineBase):
    async def hpss(
        self,
        raw: bytes,
        filename: str,
        *,
        margin: float = 1.0,
        kernel_size: int = 31,
        output_format: str = "wav",
    ) -> dict[str, bytes]:
        self._log.info(
            "hpss start: filename=%s input_bytes=%d margin=%.3f "
            "kernel_size=%d output_format=%s",
            filename, len(raw), margin, kernel_size, output_format,
        )
        t0 = time.perf_counter()
        async with self._lock:
            result = await asyncio.to_thread(
                self._hpss_sync, raw, filename, margin, kernel_size, output_format
            )
            self._touch()
            self._log.info(
                "hpss done: filename=%s duration_ms=%.1f "
                "harmonic_bytes=%d percussive_bytes=%d",
                filename, (time.perf_counter() - t0) * 1000.0,
                len(result.get("harmonic", b"")),
                len(result.get("percussive", b"")),
            )
            return result

    def _hpss_sync(
        self,
        raw: bytes,
        filename: str,
        margin: float,
        kernel_size: int,
        output_format: str,
    ) -> dict[str, bytes]:
        import librosa
        import numpy as np
        import soundfile as sf

        wav_path = to_wav_float32(raw, filename)
        try:
            y, sr = librosa.load(wav_path, sr=None, mono=False)

            if y.ndim == 1:
                y_harm, y_perc = librosa.effects.hpss(
                    y, margin=margin, kernel_size=kernel_size
                )
            else:
                harm_chs, perc_chs = [], []
                for ch in y:
                    h, p = librosa.effects.hpss(ch, margin=margin, kernel_size=kernel_size)
                    harm_chs.append(h)
                    perc_chs.append(p)
                y_harm = np.stack(harm_chs, axis=0)
                y_perc = np.stack(perc_chs, axis=0)

            results: dict[str, bytes] = {}
            for stem, audio in (("harmonic", y_harm), ("percussive", y_perc)):
                fd, tmp = tempfile.mkstemp(prefix=f"audiolla-hpss-{stem}-", suffix=".wav")
                os.close(fd)
                try:
                    if audio.ndim == 1:
                        sf.write(tmp, audio, sr, subtype="PCM_16")
                    else:
                        sf.write(tmp, audio.T, sr, subtype="PCM_16")
                    audio_bytes, _ = encode_audio(tmp, output_format)
                    results[stem] = audio_bytes
                finally:
                    try:
                        os.unlink(tmp)
                    except OSError:
                        pass
            return results

        except AudioConversionError:
            raise
        except Exception as exc:
            self._log.exception("HPSS failed for %s", filename)
            raise AudioConversionError(f"HPSS failed: {exc}") from exc
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass
