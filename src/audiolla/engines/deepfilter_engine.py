"""DeepFilterNet engine — neural speech and vocal enhancement.

Wraps the ``deepfilternet`` library (DF3 model) for real-time-grade deep
learning noise suppression and speech/vocal enhancement.  Better than UVR
for speech-focused sources; processes the full mix if non-speech sources
are present.

Model and df state are initialised in ``_load_sync()`` via ``init_df()``
which downloads the DF3 weights on first use.
"""

from __future__ import annotations

import asyncio
import os
import tempfile

from ..audio import AudioConversionError, encode_audio, to_wav_float32
from .base import EngineBase


class DeepFilterError(AudioConversionError):
    """DeepFilterNet inference failed."""


class DeepFilterNetEngine(EngineBase):
    def _load_sync(self) -> object:
        from df.enhance import enhance, init_df  # noqa: PLC0415

        self._model, self._df_state, _ = init_df()
        self._enhance = enhance
        self._log.info(
            "DeepFilterNet engine ready (sr=%d)", self._df_state.sr()
        )
        return self._model

    async def enhance(
        self,
        raw: bytes,
        filename: str,
        *,
        output_format: str = "wav",
    ) -> bytes:
        """Enhance speech/vocals via DeepFilterNet DF3.

        Returns enhanced audio bytes in ``output_format``.
        """
        await self.get_model()
        async with self._lock:
            result = await asyncio.to_thread(
                self._enhance_sync,
                raw,
                filename,
                output_format,
            )
            self._touch()
            return result

    def _enhance_sync(
        self,
        raw: bytes,
        filename: str,
        output_format: str,
    ) -> bytes:
        import soundfile as sf  # noqa: PLC0415
        import torch  # noqa: PLC0415

        wav_path: str | None = None
        out_path: str | None = None
        try:
            wav_path = to_wav_float32(raw, filename)

            audio, sr = sf.read(wav_path, dtype="float32", always_2d=True)
            # (samples, channels) → (channels, samples) for DF
            audio_t = torch.from_numpy(audio.T)

            if sr != self._df_state.sr():
                import torchaudio  # noqa: PLC0415

                audio_t = torchaudio.functional.resample(
                    audio_t, sr, self._df_state.sr()
                )

            enhanced = self._enhance(self._model, self._df_state, audio_t)
            # (channels, samples) → (samples, channels)
            enhanced_np = enhanced.numpy().T

            out_fd, out_path = tempfile.mkstemp(
                prefix="audiolla-df-", suffix=".wav"
            )
            os.close(out_fd)
            sf.write(out_path, enhanced_np, self._df_state.sr())

            audio_bytes, _ = encode_audio(out_path, output_format)
            return audio_bytes
        except AudioConversionError:
            raise
        except Exception as exc:
            raise DeepFilterError(
                f"DeepFilterNet inference failed: {exc}"
            ) from exc
        finally:
            if wav_path and os.path.exists(wav_path):
                os.unlink(wav_path)
            if out_path and os.path.exists(out_path):
                os.unlink(out_path)
