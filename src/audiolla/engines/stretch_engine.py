"""Time-stretch and pitch-shift engine using librosa phase vocoder.

Applies time-scale modification (tempo_factor) and/or pitch shifting
(pitch_semitones) independently. Each channel is processed separately
so stereo files stay stereo.
"""
from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

from ..audio import AudioConversionError, encode_audio, write_temp_input
from .base import EngineBase


class StretchEngine(EngineBase):
    def _load_sync(self) -> object:
        import librosa  # noqa: PLC0415
        import soundfile as sf  # noqa: PLC0415

        self._librosa = librosa
        self._sf = sf
        self._log.info("StretchEngine ready (librosa %s)", librosa.__version__)
        return librosa

    async def stretch(
        self,
        raw: bytes,
        filename: str,
        *,
        tempo_factor: float = 1.0,
        pitch_semitones: float = 0.0,
        output_format: str = "wav",
    ) -> bytes:
        await self.get_model()
        result = await asyncio.to_thread(
            self._stretch_sync, raw, filename, tempo_factor, pitch_semitones, output_format
        )
        self._touch()
        return result

    def _stretch_sync(
        self,
        raw: bytes,
        filename: str,
        tempo_factor: float,
        pitch_semitones: float,
        output_format: str,
    ) -> bytes:
        import numpy as np  # noqa: PLC0415

        librosa = self._librosa
        sf = self._sf

        in_path: str | None = None
        wav_path: str | None = None
        try:
            in_path = write_temp_input(raw, filename)
            y, sr = librosa.load(in_path, sr=None, mono=False)

            channels: list[Any] = [y] if y.ndim == 1 else list(y)

            processed: list[Any] = []
            for ch in channels:
                out = ch
                if tempo_factor != 1.0:
                    out = librosa.effects.time_stretch(out, rate=tempo_factor)
                if pitch_semitones != 0.0:
                    out = librosa.effects.pitch_shift(out, sr=sr, n_steps=pitch_semitones)
                processed.append(out)

            min_len = min(len(c) for c in processed)
            processed = [c[:min_len] for c in processed]
            y_out = processed[0] if len(processed) == 1 else np.stack(processed)

            wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-stretch-", suffix=".wav")
            os.close(wav_fd)
            data = y_out if y_out.ndim == 1 else y_out.T
            sf.write(wav_path, data, sr, subtype="FLOAT")

            result_bytes, _ = encode_audio(wav_path, output_format)
            return result_bytes

        except AudioConversionError:
            raise
        except Exception as exc:
            raise AudioConversionError(f"stretch failed: {exc}") from exc
        finally:
            if in_path and os.path.exists(in_path):
                os.unlink(in_path)
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)
