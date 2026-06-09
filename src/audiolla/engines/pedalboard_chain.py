"""Pedalboard preset-based mastering engine (pedalboard 0.9.20, GPL v3).

Two built-in presets:
  transparent — light compression + a 1.5 dB shelf at 8 kHz + true-peak
                limiter at -1 dBTP. Default target -14 LUFS (streaming).
  loud        — harder 4:1 compression + 2.5 dB shelf at 9 kHz + limiter
                at -0.3 dBTP. Default target -8 LUFS (broadcast/club).

Presets are pure-Python pedalboard chains — no weights. CPU-only.
`get_model()` is a no-op; `loaded()` always returns False.

Note: pedalboard is GPL v3. Same caveat as matchering — fine for
self-hosted; distribution requires GPL compliance review.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from typing import Any

from ..audio import AudioConversionError, encode_audio, to_wav_float32
from .base import EngineBase


_PRESET_TARGET_LUFS = {
    "transparent": -14.0,
    "loud": -8.0,
}


class PedalboardChainEngine(EngineBase):
    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)

    async def master_chain(
        self,
        raw: bytes,
        filename: str,
        *,
        preset: str,
        target_lufs: float | None = None,
        output_format: str = "wav",
    ) -> bytes:
        if preset not in _PRESET_TARGET_LUFS:
            self._log.warning("master_chain: unknown preset %r", preset)
            raise AudioConversionError(
                f"unknown preset {preset!r}; available: {list(_PRESET_TARGET_LUFS)}"
            )
        self._log.info(
            "master_chain start: filename=%s input_bytes=%d preset=%s "
            "target_lufs=%s output_format=%s",
            filename, len(raw), preset, target_lufs, output_format,
        )
        t0 = time.perf_counter()
        async with self._lock:
            result = await asyncio.to_thread(
                self._master_sync, raw, filename, preset, target_lufs, output_format,
            )
            self._touch()
            self._log.info(
                "master_chain done: filename=%s duration_ms=%.1f output_bytes=%d",
                filename, (time.perf_counter() - t0) * 1000.0, len(result),
            )
            return result

    def _master_sync(
        self,
        raw: bytes,
        filename: str,
        preset: str,
        target_lufs: float | None,
        output_format: str,
    ) -> bytes:
        import numpy as np
        import pyloudnorm as pyln
        import soundfile as sf

        wav_path = to_wav_float32(raw, filename)
        out_fd, out_wav = tempfile.mkstemp(prefix="audiolla-pb-", suffix=".wav")
        os.close(out_fd)

        try:
            audio, sr = sf.read(wav_path, always_2d=False, dtype="float32")
            if audio.ndim == 1:
                audio = np.stack([audio, audio], axis=-1)

            board = self._build_preset(preset)
            # pedalboard wants (samples, channels) — soundfile returns it that way.
            processed = board(audio, sample_rate=sr)

            # LUFS normalization to the requested target (or the preset default).
            target = target_lufs if target_lufs is not None else _PRESET_TARGET_LUFS[preset]
            meter = pyln.Meter(sr)
            current_lufs = meter.integrated_loudness(processed)
            if np.isfinite(current_lufs):
                processed = pyln.normalize.loudness(processed, current_lufs, target)

            np.clip(processed, -1.0, 1.0, out=processed)
            sf.write(out_wav, processed, sr, subtype="PCM_16")
            audio_bytes, _ct = encode_audio(out_wav, output_format)
            return audio_bytes
        finally:
            for p in (wav_path, out_wav):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    def _build_preset(self, preset: str) -> Any:
        from pedalboard import (
            Compressor, Gain, HighShelfFilter, Limiter, Pedalboard,
        )

        if preset == "transparent":
            return Pedalboard([
                Compressor(threshold_db=-18, ratio=2.0, attack_ms=20, release_ms=200),
                HighShelfFilter(cutoff_frequency_hz=8000, gain_db=1.5),
                Gain(gain_db=2.0),
                Limiter(threshold_db=-1.0, release_ms=100),
            ])
        if preset == "loud":
            return Pedalboard([
                Compressor(threshold_db=-24, ratio=4.0, attack_ms=5, release_ms=120),
                HighShelfFilter(cutoff_frequency_hz=9000, gain_db=2.5),
                Gain(gain_db=4.0),
                Limiter(threshold_db=-0.3, release_ms=50),
            ])
        raise AudioConversionError(f"unknown preset {preset!r}")
