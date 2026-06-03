"""Audio tagging engine via Audio Spectrogram Transformer (AST).

Model: MIT/ast-finetuned-audioset-10-10-0.4593
Returns top-K AudioSet class labels with confidence scores.

Requires HF model cache (set HF_HUB_OFFLINE=0 on first run to download).
"""
from __future__ import annotations

import asyncio
import os

from ..audio import AudioConversionError, write_temp_input
from .base import EngineBase

_MODEL_ID = "MIT/ast-finetuned-audioset-10-10-0.4593"


class TagEngine(EngineBase):
    def _load_sync(self) -> object:
        from transformers import (  # noqa: PLC0415
            AutoFeatureExtractor,
            AutoModelForAudioClassification,
        )
        import torch  # noqa: PLC0415

        self._extractor = AutoFeatureExtractor.from_pretrained(_MODEL_ID)
        model = AutoModelForAudioClassification.from_pretrained(_MODEL_ID)
        model.eval()
        self._torch = torch
        self._log.info("TagEngine ready (AST %s)", _MODEL_ID)
        return model

    def _release_model(self, model: object) -> None:
        try:
            model.cpu()  # type: ignore[union-attr]
        except Exception:
            pass

    async def tag(
        self,
        raw: bytes,
        filename: str,
        *,
        top_k: int = 10,
    ) -> dict:
        model = await self.get_model()
        result = await asyncio.to_thread(self._tag_sync, raw, filename, top_k, model)
        self._touch()
        return result

    def _tag_sync(self, raw: bytes, filename: str, top_k: int, model: object) -> dict:
        import librosa  # noqa: PLC0415

        torch = self._torch
        in_path: str | None = None
        try:
            in_path = write_temp_input(raw, filename)
            y, _ = librosa.load(in_path, sr=16000, mono=True)

            inputs = self._extractor(y, sampling_rate=16000, return_tensors="pt")
            with torch.no_grad():
                logits = model(**inputs).logits  # type: ignore[operator]
            scores = torch.softmax(logits, dim=-1)[0]
            top_k = min(top_k, scores.shape[0])
            top_indices = scores.topk(top_k).indices.tolist()

            tags = [
                {
                    "label": model.config.id2label[i],  # type: ignore[union-attr]
                    "score": round(scores[i].item(), 4),
                }
                for i in top_indices
            ]
            return {"tags": tags, "duration": round(float(len(y) / 16000), 3)}

        except AudioConversionError:
            raise
        except Exception as exc:
            raise AudioConversionError(f"audio tagging failed: {exc}") from exc
        finally:
            if in_path and os.path.exists(in_path):
                os.unlink(in_path)
