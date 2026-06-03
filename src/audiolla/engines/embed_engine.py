"""Audio embedding engine via LAION CLAP.

Model: laion/larger_clap_music_and_speech
Returns a 512-dim L2-normalised float vector. With query_text, also returns
the cosine similarity between the audio and the text description.

Requires HF model cache (set HF_HUB_OFFLINE=0 on first run to download).
"""
from __future__ import annotations

import asyncio
import os

from ..audio import AudioConversionError, write_temp_input
from .base import EngineBase

_MODEL_ID = "laion/larger_clap_music_and_speech"


class EmbedEngine(EngineBase):
    def _load_sync(self) -> object:
        from transformers import ClapModel, ClapProcessor  # noqa: PLC0415
        import torch  # noqa: PLC0415

        self._processor = ClapProcessor.from_pretrained(_MODEL_ID)
        model = ClapModel.from_pretrained(_MODEL_ID)
        model.eval()
        self._torch = torch
        self._log.info("EmbedEngine ready (CLAP %s)", _MODEL_ID)
        return model

    def _release_model(self, model: object) -> None:
        try:
            model.cpu()  # type: ignore[union-attr]
        except Exception:
            pass

    async def embed(
        self,
        raw: bytes,
        filename: str,
        *,
        query_text: str | None = None,
    ) -> dict:
        model = await self.get_model()
        result = await asyncio.to_thread(self._embed_sync, raw, filename, query_text, model)
        self._touch()
        return result

    def _embed_sync(
        self, raw: bytes, filename: str, query_text: str | None, model: object
    ) -> dict:
        import librosa  # noqa: PLC0415

        torch = self._torch
        in_path: str | None = None
        try:
            in_path = write_temp_input(raw, filename)
            y, _ = librosa.load(in_path, sr=48000, mono=True)

            inputs = self._processor(audios=y, return_tensors="pt", sampling_rate=48000)
            with torch.no_grad():
                audio_features = model.get_audio_features(**inputs)  # type: ignore[union-attr]
            audio_features = audio_features / audio_features.norm(p=2, dim=-1, keepdim=True)
            embedding = audio_features[0].tolist()

            result: dict = {"embedding": embedding, "dim": len(embedding)}

            if query_text:
                text_inputs = self._processor(
                    text=[query_text], return_tensors="pt", padding=True
                )
                with torch.no_grad():
                    text_features = model.get_text_features(  # type: ignore[union-attr]
                        **text_inputs
                    )
                text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)
                similarity = (audio_features @ text_features.T)[0, 0].item()
                result["similarity"] = round(float(similarity), 4)
                result["query_text"] = query_text

            return result

        except AudioConversionError:
            raise
        except Exception as exc:
            raise AudioConversionError(f"audio embedding failed: {exc}") from exc
        finally:
            if in_path and os.path.exists(in_path):
                os.unlink(in_path)
