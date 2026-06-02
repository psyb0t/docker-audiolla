"""Speaker diarization engine via pyannote.audio.

Lazy-loads the pyannote/speaker-diarization-3.1 pipeline on first call.
Requires a valid HuggingFace token in the HUGGINGFACE_TOKEN environment
variable and acceptance of the model's usage terms on the HF Hub.
"""

from __future__ import annotations

import asyncio
import os

from ..audio import AudioConversionError, to_wav_float32
from .base import EngineBase


class DiarizeError(AudioConversionError):
    """Speaker diarization failed."""


class DiarizeEngine(EngineBase):
    def _load_sync(self) -> object:
        from pyannote.audio import Pipeline  # noqa: PLC0415

        token = os.environ.get("HUGGINGFACE_TOKEN", "")
        if not token:
            raise DiarizeError(
                "HUGGINGFACE_TOKEN env var is required for pyannote diarization"
            )
        pipeline = Pipeline.from_pretrained(
            "pyannote/speaker-diarization-3.1",
            use_auth_token=token,
        )
        self._pipeline = pipeline
        self._log.info("DiarizeEngine ready (pyannote/speaker-diarization-3.1)")
        return pipeline

    async def diarize(
        self,
        raw: bytes,
        filename: str,
        *,
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> dict:
        await self.get_model()
        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            self._diarize_sync,
            raw,
            filename,
            num_speakers,
            min_speakers,
            max_speakers,
        )
        self._touch()
        return result

    def _diarize_sync(
        self,
        raw: bytes,
        filename: str,
        num_speakers: int | None,
        min_speakers: int | None,
        max_speakers: int | None,
    ) -> dict:
        wav_path: str | None = None
        try:
            wav_path = to_wav_float32(raw, filename)
            kwargs: dict = {}
            if num_speakers is not None:
                kwargs["num_speakers"] = num_speakers
            if min_speakers is not None:
                kwargs["min_speakers"] = min_speakers
            if max_speakers is not None:
                kwargs["max_speakers"] = max_speakers

            diarization = self._pipeline(wav_path, **kwargs)

            segments: list[dict] = []
            speaker_set: set[str] = set()
            for turn, _, speaker in diarization.itertracks(yield_label=True):
                segments.append({
                    "speaker": speaker,
                    "start_sec": round(turn.start, 3),
                    "end_sec": round(turn.end, 3),
                    "duration_sec": round(turn.end - turn.start, 3),
                })
                speaker_set.add(speaker)

            segments.sort(key=lambda s: s["start_sec"])

            return {
                "segments": segments,
                "num_speakers": len(speaker_set),
                "speakers": sorted(speaker_set),
                "duration": round(segments[-1]["end_sec"] if segments else 0.0, 3),
            }
        except AudioConversionError:
            raise
        except Exception as exc:
            raise DiarizeError(f"speaker diarization failed: {exc}") from exc
        finally:
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)
