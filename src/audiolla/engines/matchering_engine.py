"""matchering reference-based mastering engine (matchering 2.0.6, GPL v3).

matchering matches a target track's loudness, EQ curve, peak, and stereo
width to a reference song. CPU-only, no model weights. Both target and
reference must be ≥ 2 seconds and stereo 44.1 kHz (we resample at ingress).

Note: matchering is GPL v3. For internal / self-hosted use this is fine.
Distribution of the image as a product requires GPL compliance review.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from ..audio import AudioConversionError, encode_audio, to_wav_float32
from .base import EngineBase


class MatcheringEngine(EngineBase):
    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)

    async def master_reference(
        self,
        raw: bytes,
        filename: str,
        ref_raw: bytes,
        ref_filename: str,
        *,
        target_lufs: float | None = None,
        output_format: str = "wav",
    ) -> bytes:
        async with self._lock:
            result = await asyncio.to_thread(
                self._master_sync,
                raw, filename, ref_raw, ref_filename,
                target_lufs, output_format,
            )
            self._touch()
            return result

    def _master_sync(
        self,
        raw: bytes,
        filename: str,
        ref_raw: bytes,
        ref_filename: str,
        target_lufs: float | None,
        output_format: str,
    ) -> bytes:
        import matchering as mg

        target_wav = to_wav_float32(raw, filename)
        reference_wav = to_wav_float32(ref_raw, ref_filename)
        out_fd, out_wav = tempfile.mkstemp(prefix="audiolla-mastered-", suffix=".wav")
        os.close(out_fd)

        try:
            try:
                mg.process(
                    target=target_wav,
                    reference=reference_wav,
                    results=[mg.pcm16(out_wav)],
                )
            except Exception as exc:  # noqa: BLE001
                msg = str(exc).lower()
                if "validation" in msg or "fft_size" in msg or "short" in msg:
                    raise AudioConversionError(
                        f"matchering validation failed: {exc}. "
                        "Both target and reference must be stereo, ≥ ~5 seconds, "
                        "and a supported audio format."
                    ) from exc
                raise AudioConversionError(f"matchering failed: {exc}") from exc

            if target_lufs is not None:
                _normalize_wav_to_lufs(out_wav, target_lufs)

            audio_bytes, _ct = encode_audio(out_wav, output_format)
            return audio_bytes
        finally:
            for p in (target_wav, reference_wav, out_wav):
                try:
                    os.unlink(p)
                except OSError:
                    pass


def _normalize_wav_to_lufs(wav_path: str, target_lufs: float) -> None:
    """Re-write the WAV at `wav_path` to hit ``target_lufs`` integrated LUFS.

    pyloudnorm meters at the WAV's native sample rate. Result is written
    back in-place via soundfile (we keep 16-bit / 32-bit precision based
    on what was already there).
    """
    import numpy as np
    import pyloudnorm as pyln
    import soundfile as sf

    audio, sr = sf.read(wav_path, always_2d=False)
    meter = pyln.Meter(sr)
    current_lufs = meter.integrated_loudness(audio)
    if not np.isfinite(current_lufs):
        return
    normalized = pyln.normalize.loudness(audio, current_lufs, target_lufs)
    np.clip(normalized, -1.0, 1.0, out=normalized)
    sf.write(wav_path, normalized, sr, subtype="PCM_16")
