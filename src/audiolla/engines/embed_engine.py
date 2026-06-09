"""Audio embedding engine via LAION CLAP.

Model: laion/larger_clap_music_and_speech
Returns a 512-dim L2-normalised float vector. With query_text, also returns
the cosine similarity between the audio and the text description.

Requires HF model cache (set HF_HUB_OFFLINE=0 on first run to download).
"""
from __future__ import annotations

import asyncio
import os
import time

from ..audio import AudioConversionError, write_temp_input
from .base import EngineBase

_MODEL_ID = "laion/larger_clap_music_and_speech"


class EmbedEngine(EngineBase):
    def _load_sync(self) -> object:
        from transformers import ClapModel, ClapProcessor  # noqa: PLC0415
        import torch  # noqa: PLC0415

        self._log.info("loading CLAP model %s", _MODEL_ID)
        self._processor = ClapProcessor.from_pretrained(_MODEL_ID)
        model = ClapModel.from_pretrained(_MODEL_ID)
        model.eval()
        self._torch = torch
        self._log.info("EmbedEngine ready (CLAP %s)", _MODEL_ID)
        return model

    def _release_model(self, model: object) -> None:
        try:
            model.cpu()  # type: ignore[union-attr]
        except Exception:  # noqa: BLE001
            self._log.exception("CLAP model.cpu() failed")

    async def embed(
        self,
        raw: bytes,
        filename: str,
        *,
        query_text: str | None = None,
    ) -> dict:
        qt_display = (query_text or "")[:80]
        self._log.info(
            "embed start: filename=%s input_bytes=%d query_text_len=%d query_text_head=%r",
            filename, len(raw), len(query_text or ""), qt_display,
        )
        t0 = time.perf_counter()
        model = await self.get_model()
        result = await asyncio.to_thread(self._embed_sync, raw, filename, query_text, model)
        self._touch()
        self._log.info(
            "embed done: filename=%s duration_ms=%.1f dim=%d has_similarity=%s",
            filename, (time.perf_counter() - t0) * 1000.0,
            int(result.get("dim", 0)), "similarity" in result,
        )
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
            self._log.exception("audio embedding failed for %s", filename)
            raise AudioConversionError(f"audio embedding failed: {exc}") from exc
        finally:
            if in_path and os.path.exists(in_path):
                os.unlink(in_path)

    async def similar(
        self,
        raw_a: bytes, filename_a: str,
        raw_b: bytes, filename_b: str,
    ) -> dict:
        """Cosine similarity between two audio files via CLAP embeddings.
        Both embeddings are L2-normalised so cosine similarity = dot product."""
        self._log.info(
            "similar start: file_a=%s bytes_a=%d file_b=%s bytes_b=%d",
            filename_a, len(raw_a), filename_b, len(raw_b),
        )
        t0 = time.perf_counter()
        model = await self.get_model()
        result = await asyncio.to_thread(
            self._similar_sync, raw_a, filename_a, raw_b, filename_b, model
        )
        self._touch()
        self._log.info(
            "similar done: file_a=%s file_b=%s duration_ms=%.1f similarity=%.4f",
            filename_a, filename_b, (time.perf_counter() - t0) * 1000.0,
            float(result.get("similarity", 0.0)),
        )
        return result

    def _similar_sync(
        self, raw_a: bytes, filename_a: str, raw_b: bytes, filename_b: str, model: object
    ) -> dict:
        import librosa  # noqa: PLC0415

        torch = self._torch
        path_a: str | None = None
        path_b: str | None = None
        try:
            path_a = write_temp_input(raw_a, filename_a)
            y_a, _ = librosa.load(path_a, sr=48000, mono=True)
            inputs_a = self._processor(audios=y_a, return_tensors="pt", sampling_rate=48000)
            with torch.no_grad():
                feats_a = model.get_audio_features(**inputs_a)  # type: ignore[union-attr]
            feats_a = feats_a / feats_a.norm(p=2, dim=-1, keepdim=True)
            emb_a = feats_a[0].tolist()

            path_b = write_temp_input(raw_b, filename_b)
            y_b, _ = librosa.load(path_b, sr=48000, mono=True)
            inputs_b = self._processor(audios=y_b, return_tensors="pt", sampling_rate=48000)
            with torch.no_grad():
                feats_b = model.get_audio_features(**inputs_b)  # type: ignore[union-attr]
            feats_b = feats_b / feats_b.norm(p=2, dim=-1, keepdim=True)

            similarity = (feats_a @ feats_b.T)[0, 0].item()
            return {"similarity": round(float(similarity), 4), "dim": len(emb_a)}

        except AudioConversionError:
            raise
        except Exception as exc:
            self._log.exception(
                "audio similarity failed: file_a=%s file_b=%s",
                filename_a, filename_b,
            )
            raise AudioConversionError(f"audio similarity failed: {exc}") from exc
        finally:
            if path_a and os.path.exists(path_a):
                os.unlink(path_a)
            if path_b and os.path.exists(path_b):
                os.unlink(path_b)

    async def classify(
        self,
        raw: bytes,
        filename: str,
        *,
        labels: list[str],
    ) -> dict:
        self._log.info(
            "classify start: filename=%s input_bytes=%d n_labels=%d",
            filename, len(raw), len(labels),
        )
        t0 = time.perf_counter()
        model = await self.get_model()
        result = await asyncio.to_thread(self._classify_sync, raw, filename, labels, model)
        self._touch()
        top = (result.get("results") or [{}])[0]
        self._log.info(
            "classify done: filename=%s duration_ms=%.1f top_label=%s top_score=%.4f",
            filename, (time.perf_counter() - t0) * 1000.0,
            top.get("label"), float(top.get("score", 0.0)),
        )
        return result

    def _classify_sync(
        self, raw: bytes, filename: str, labels: list[str], model: object
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

            text_inputs = self._processor(
                text=labels, return_tensors="pt", padding=True
            )
            with torch.no_grad():
                text_features = model.get_text_features(  # type: ignore[union-attr]
                    **text_inputs
                )
            text_features = text_features / text_features.norm(p=2, dim=-1, keepdim=True)

            similarities = (audio_features @ text_features.T)[0].tolist()
            scored = sorted(
                [
                    {"label": lbl, "score": round(float(sim), 4)}
                    for lbl, sim in zip(labels, similarities)
                ],
                key=lambda x: x["score"],
                reverse=True,
            )
            return {"results": scored}

        except AudioConversionError:
            raise
        except Exception as exc:
            self._log.exception("audio classification failed for %s", filename)
            raise AudioConversionError(f"audio classification failed: {exc}") from exc
        finally:
            if in_path and os.path.exists(in_path):
                os.unlink(in_path)
