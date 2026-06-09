"""Voice Activity Detection engine via silero-vad.

Lazy-loads the silero-vad model on first call. Detects speech and
non-speech segments, returning timestamps and overall speech ratio.
"""

from __future__ import annotations

import asyncio
import os
import time

from ..audio import AudioConversionError, to_wav_float32
from .base import EngineBase


class VADError(AudioConversionError):
    """Voice activity detection failed."""


class VADEngine(EngineBase):
    def _load_sync(self) -> object:
        import torch  # noqa: PLC0415
        from silero_vad import get_speech_timestamps, load_silero_vad, read_audio  # noqa: PLC0415

        self._log.info("loading silero-vad ...")
        model = load_silero_vad()
        self._model = model
        self._torch = torch
        self._get_speech_timestamps = get_speech_timestamps
        self._read_audio = read_audio
        self._log.info("VADEngine ready (silero-vad)")
        return model

    async def detect_voice(
        self,
        raw: bytes,
        filename: str,
        *,
        threshold: float = 0.5,
        min_speech_duration_ms: float = 250.0,
        min_silence_duration_ms: float = 100.0,
    ) -> dict:
        self._log.info(
            "detect_voice start: filename=%s input_bytes=%d threshold=%.3f "
            "min_speech_ms=%.1f min_silence_ms=%.1f",
            filename, len(raw), threshold,
            min_speech_duration_ms, min_silence_duration_ms,
        )
        t0 = time.perf_counter()
        await self.get_model()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._detect_voice_sync,
            raw,
            filename,
            threshold,
            min_speech_duration_ms,
            min_silence_duration_ms,
        )
        self._touch()
        self._log.info(
            "detect_voice done: filename=%s duration_ms=%.1f "
            "speech_segments=%d speech_ratio=%.3f",
            filename, (time.perf_counter() - t0) * 1000.0,
            len(result.get("speech_segments", [])),
            result.get("speech_ratio", 0.0),
        )
        return result

    def _detect_voice_sync(
        self,
        raw: bytes,
        filename: str,
        threshold: float,
        min_speech_duration_ms: float,
        min_silence_duration_ms: float,
    ) -> dict:
        wav_path: str | None = None
        try:
            wav_path = to_wav_float32(raw, filename)
            audio = self._read_audio(wav_path, sampling_rate=16000)

            speech_timestamps = self._get_speech_timestamps(
                audio,
                self._model,
                threshold=threshold,
                min_speech_duration_ms=int(min_speech_duration_ms),
                min_silence_duration_ms=int(min_silence_duration_ms),
                return_seconds=True,
            )

            speech_segs = [
                {
                    "start_sec": s["start"],
                    "end_sec": s["end"],
                    "duration_sec": s["end"] - s["start"],
                }
                for s in speech_timestamps
            ]
            total_speech = sum(s["duration_sec"] for s in speech_segs)
            duration = float(len(audio)) / 16000.0

            non_speech: list[dict] = []
            cursor = 0.0
            for seg in speech_segs:
                if seg["start_sec"] > cursor:
                    non_speech.append({
                        "start_sec": cursor,
                        "end_sec": seg["start_sec"],
                        "duration_sec": seg["start_sec"] - cursor,
                    })
                cursor = seg["end_sec"]
            if cursor < duration:
                non_speech.append({
                    "start_sec": cursor,
                    "end_sec": duration,
                    "duration_sec": duration - cursor,
                })

            return {
                "speech_segments": speech_segs,
                "non_speech_segments": non_speech,
                "speech_ratio": total_speech / duration if duration > 0 else 0.0,
                "duration": duration,
                "threshold": threshold,
            }
        except AudioConversionError:
            raise
        except Exception as exc:
            self._log.exception("voice activity detection failed for %s", filename)
            raise VADError(f"voice activity detection failed: {exc}") from exc
        finally:
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)
