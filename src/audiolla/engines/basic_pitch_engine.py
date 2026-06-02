"""basic-pitch engine — polyphonic audio-to-MIDI transcription.

Wraps Spotify's basic-pitch library (ONNX backend) to convert any audio
source (guitar, piano, voice, full mix) to a polyphonic Standard MIDI File.

The ONNX backend is used (``basic-pitch[onnx]``) so there is no TensorFlow
dependency.  The model is lazy-loaded on first predict call by basic-pitch
itself; ``_load_sync()`` only verifies the import and stores the callable.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from ..audio import AudioConversionError, to_wav_float32
from .base import EngineBase


class BasicPitchError(AudioConversionError):
    """basic-pitch inference failed."""


class BasicPitchEngine(EngineBase):
    def _load_sync(self) -> object:
        from basic_pitch import ICASSP_2022_MODEL_PATH  # noqa: PLC0415
        from basic_pitch.inference import predict as _predict  # noqa: PLC0415

        self._predict = _predict
        self._model_path = ICASSP_2022_MODEL_PATH
        self._log.info("basic-pitch engine ready (ONNX backend)")
        return _predict

    async def to_midi(
        self,
        raw: bytes,
        filename: str,
        *,
        onset_threshold: float = 0.5,
        frame_threshold: float = 0.3,
        minimum_note_length_ms: float = 58.0,
        minimum_frequency: float | None = None,
        maximum_frequency: float | None = None,
        multiple_pitch_bends: bool = False,
        melodia_trick: bool = True,
    ) -> bytes:
        """Convert audio bytes to a polyphonic MIDI file.

        Returns raw MIDI bytes.
        """
        await self.get_model()
        async with self._lock:
            result = await asyncio.to_thread(
                self._to_midi_sync,
                raw,
                filename,
                onset_threshold,
                frame_threshold,
                minimum_note_length_ms,
                minimum_frequency,
                maximum_frequency,
                multiple_pitch_bends,
                melodia_trick,
            )
            self._touch()
            return result

    def _to_midi_sync(
        self,
        raw: bytes,
        filename: str,
        onset_threshold: float,
        frame_threshold: float,
        minimum_note_length_ms: float,
        minimum_frequency: float | None,
        maximum_frequency: float | None,
        multiple_pitch_bends: bool,
        melodia_trick: bool,
    ) -> bytes:
        wav_path: str | None = None
        out_path: str | None = None
        try:
            wav_path = to_wav_float32(raw, filename)

            out_fd, out_path = tempfile.mkstemp(
                prefix="audiolla-midi-", suffix=".mid"
            )
            os.close(out_fd)

            _, midi_data, _ = self._predict(
                wav_path,
                self._model_path,
                onset_threshold=onset_threshold,
                frame_threshold=frame_threshold,
                minimum_note_length=minimum_note_length_ms,
                minimum_frequency=minimum_frequency,
                maximum_frequency=maximum_frequency,
                multiple_pitch_bends=multiple_pitch_bends,
                melodia_trick=melodia_trick,
            )
            midi_data.write(out_path)
            with open(out_path, "rb") as fh:
                return fh.read()
        except AudioConversionError:
            raise
        except Exception as exc:
            raise BasicPitchError(f"basic-pitch inference failed: {exc}") from exc
        finally:
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)
            if out_path and os.path.exists(out_path):
                os.unlink(out_path)
