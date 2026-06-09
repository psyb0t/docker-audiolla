"""Demucs stem separation engine (adefossez/demucs, MIT license).

Uses the lower-level demucs 4.0.1 API:
  * ``demucs.pretrained.get_model(name)`` — loads htdemucs / htdemucs_ft /
    htdemucs_6s / mdx_extra. Downloads from ``dl.fbaipublicfiles.com`` on
    cold start; cached to ``$TORCH_HOME/hub/checkpoints/`` (entrypoint
    points ``TORCH_HOME`` at the persistent /data volume).
  * ``demucs.audio.AudioFile(track).read(...)`` — ffmpeg-backed audio
    decode at the model's native samplerate / channel count (44.1 kHz
    stereo for every variant).
  * ``demucs.apply.apply_model(model, wav[None], ...)`` — runs inference
    and returns ``Tensor(batch, sources, channels, samples)``. We strip
    the leading batch dim, then zip with ``model.sources``.

Each call runs inside ``asyncio.to_thread`` so the event loop stays
unblocked. The per-engine asyncio.Lock (in EngineBase) serialises GPU
access within the process.

``demucs.api.Separator`` does NOT exist in the released 4.0.1 wheel — it
was added on the main branch later. Don't import it.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
from pathlib import Path
from typing import Any

from ..audio import AudioConversionError, encode_audio, to_wav_float32
from .base import EngineBase


# Match demucs' CLI default for apply_model() — overlap=0.25, shifts=0, split=True.
_APPLY_KWARGS = dict(shifts=0, split=True, overlap=0.25, progress=False)


class DemucsEngine(EngineBase):
    def __init__(
        self,
        slug: str,
        entry: dict,
        model_path: Path,
        device: str,
    ) -> None:
        super().__init__(slug, entry)
        self.model_path = model_path
        self._device = "cuda" if device.startswith("cuda") else "cpu"
        self._variant = entry.get("variant", slug)

    def _load_sync(self) -> Any:
        from demucs.pretrained import get_model

        self._log.info(
            "loading demucs variant=%s on device=%s", self._variant, self._device
        )
        model = get_model(name=self._variant)
        model.to(self._device)
        model.eval()
        self._log.info(
            "loaded demucs variant=%s samplerate=%d channels=%d sources=%s",
            self._variant, model.samplerate, model.audio_channels, list(model.sources),
        )
        return model

    def _release_model(self, model: Any) -> None:
        try:
            model.cpu()
        except Exception:  # noqa: BLE001
            self._log.exception("model.cpu() failed for %s", self.slug)
        del model

    async def separate(
        self,
        raw: bytes,
        filename: str,
        stems: list[str],
        output_format: str = "wav",
    ) -> dict[str, bytes]:
        self._log.info(
            "demucs separate start: variant=%s filename=%s input_bytes=%d "
            "stems=%s output_format=%s",
            self._variant, filename, len(raw), stems, output_format,
        )
        t0 = time.perf_counter()
        model = await self.get_model()
        async with self._lock:
            result = await asyncio.to_thread(
                self._separate_sync, model, raw, filename, stems, output_format,
            )
            self._touch()
            self._log.info(
                "demucs separate done: variant=%s filename=%s duration_ms=%.1f "
                "stems=%s total_bytes=%d",
                self._variant, filename, (time.perf_counter() - t0) * 1000.0,
                sorted(result.keys()), sum(len(v) for v in result.values()),
            )
            return result

    def _separate_sync(
        self,
        model: Any,
        raw: bytes,
        filename: str,
        stems: list[str],
        output_format: str,
    ) -> dict[str, bytes]:
        from demucs.apply import apply_model
        from demucs.audio import AudioFile

        # Decode upload to a WAV file ffmpeg likes, then let demucs' own
        # AudioFile (also ffmpeg-backed) re-read at the model's exact
        # samplerate + channel count. Going through to_wav_float32 first
        # normalises arbitrary input formats / sample rates / channel
        # layouts before demucs sees them.
        wav_path = to_wav_float32(raw, filename)
        try:
            try:
                wav = AudioFile(wav_path).read(
                    streams=0,
                    samplerate=model.samplerate,
                    channels=model.audio_channels,
                )
            except Exception as exc:  # noqa: BLE001
                # AudioFile can fall back to torchaudio if ffmpeg fails — but
                # we already normalised, so this path is a hard fail.
                self._log.exception(
                    "demucs failed to read audio: variant=%s filename=%s",
                    self._variant, filename,
                )
                raise AudioConversionError(f"demucs failed to read audio: {exc}") from exc

            # Reference normalisation — matches demucs' separate.py CLI.
            ref = wav.mean(0)
            wav_norm = (wav - ref.mean()) / (ref.std() + 1e-8)

            sources = apply_model(
                model, wav_norm[None], device=self._device,
                **_APPLY_KWARGS,
            )[0]
            sources = sources * ref.std() + ref.mean()

            available_sources = list(model.sources)
            invalid = [s for s in stems if s not in available_sources]
            if invalid:
                self._log.warning(
                    "demucs unknown stems requested: variant=%s requested=%s available=%s invalid=%s",
                    self._variant, stems, available_sources, invalid,
                )
                raise AudioConversionError(
                    f"engine {self.slug!r} model.sources={available_sources}; "
                    f"requested {invalid} are not available"
                )

            out: dict[str, bytes] = {}
            for stem in stems:
                idx = available_sources.index(stem)
                tensor = sources[idx]
                audio_bytes = self._tensor_to_format(tensor, model.samplerate, output_format)
                out[stem] = audio_bytes
            return out
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass

    def _tensor_to_format(
        self, tensor: Any, samplerate: int, output_format: str,
    ) -> bytes:
        """Persist a ``(channels, samples)`` tensor to WAV via torchaudio,
        then re-encode through ffmpeg to the requested format.
        """
        import torchaudio

        out_fd, wav_path = tempfile.mkstemp(prefix="audiolla-stem-", suffix=".wav")
        os.close(out_fd)
        try:
            torchaudio.save(
                wav_path,
                tensor.detach().cpu(),
                sample_rate=samplerate,
                format="wav",
                bits_per_sample=32,
                encoding="PCM_F",
            )
            audio_bytes, _ct = encode_audio(wav_path, output_format)
            return audio_bytes
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass
