"""UVR (audio-separator) engine — MDX/VR/Roformer model inference.

Wraps the `audio-separator` library for access to UVR ecosystem models:
de-reverb, de-echo, de-noise, karaoke, and high-quality vocal separation.

Model files download on first use and cache in UVR_MODELS_DIR
(DATA_DIR/uvr_models by default).

Two inference modes:
  restore()   — restoration model (de-reverb/de-echo/de-noise),
                returns primary (cleaned) stem as audio bytes
  separate()  — separation model (vocals/instrumental/karaoke),
                returns dict[stem_name, audio_bytes]
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import tempfile

from .. import config
from ..audio import AudioConversionError, encode_audio
from .base import EngineBase


class UVRSeparatorError(AudioConversionError):
    """Model inference failed or returned unexpected output."""


class UVRSeparatorEngine(EngineBase):
    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)
        self._model_filename: str = entry["model"]
        self._primary_stem: str | None = entry.get("primary_stem")

    def _load_sync(self) -> object:
        from audio_separator.separator import Separator  # noqa: PLC0415

        os.makedirs(config.UVR_MODELS_DIR, exist_ok=True)
        sep = Separator(
            model_file_dir=str(config.UVR_MODELS_DIR),
            output_format="WAV",
            output_single_stem=self._primary_stem,
            log_level=logging.WARNING,
        )
        self._log.info("loading UVR model %s", self._model_filename)
        sep.load_model(self._model_filename)
        self._log.info("UVR model %s ready", self._model_filename)
        return sep

    async def restore(
        self,
        raw: bytes,
        filename: str,
        *,
        output_format: str = "wav",
    ) -> bytes:
        """Run a restoration model. Returns primary (cleaned) stem bytes."""
        await self.get_model()
        async with self._lock:
            result = await asyncio.to_thread(
                self._restore_sync,
                raw,
                filename,
                output_format,
            )
            self._touch()
            return result

    def _restore_sync(self, raw: bytes, filename: str, output_format: str) -> bytes:
        with tempfile.TemporaryDirectory(prefix="audiolla-uvr-") as tmpdir:
            in_path = os.path.join(tmpdir, filename)
            with open(in_path, "wb") as fh:
                fh.write(raw)

            self._model.output_dir = tmpdir
            output_files: list[str] = self._model.separate(in_path)

            if not output_files:
                raise UVRSeparatorError(
                    f"model {self._model_filename!r} produced no output files"
                )

            target = output_files[0]
            if self._primary_stem and len(output_files) > 1:
                match = _find_stem_file(output_files, self._primary_stem)
                if match:
                    target = match

            audio_bytes, _ = encode_audio(target, output_format)
            return audio_bytes

    async def separate(
        self,
        raw: bytes,
        filename: str,
        *,
        stems: list[str] | None = None,
        output_format: str = "wav",
    ) -> dict[str, bytes]:
        """Run a separation model. Returns {stem_name: audio_bytes}."""
        await self.get_model()
        async with self._lock:
            result = await asyncio.to_thread(
                self._separate_sync,
                raw,
                filename,
                stems,
                output_format,
            )
            self._touch()
            return result

    def _separate_sync(
        self,
        raw: bytes,
        filename: str,
        stems: list[str] | None,
        output_format: str,
    ) -> dict[str, bytes]:
        with tempfile.TemporaryDirectory(prefix="audiolla-uvr-") as tmpdir:
            in_path = os.path.join(tmpdir, filename)
            with open(in_path, "wb") as fh:
                fh.write(raw)

            self._model.output_dir = tmpdir
            output_files: list[str] = self._model.separate(in_path)

            if not output_files:
                raise UVRSeparatorError(
                    f"model {self._model_filename!r} produced no output files"
                )

            result: dict[str, bytes] = {}
            for f in output_files:
                stem_name = _extract_stem_name(f)
                if stem_name is None:
                    continue
                if stems and stem_name not in stems:
                    continue
                audio_bytes, _ = encode_audio(f, output_format)
                result[stem_name] = audio_bytes

            if not result:
                raise UVRSeparatorError(
                    f"model {self._model_filename!r} produced no recognisable stems; "
                    f"files: {output_files}"
                )
            return result


_STEM_RE = re.compile(r"\(([^)]+)\)\.\w+$")


def _extract_stem_name(filepath: str) -> str | None:
    m = _STEM_RE.search(os.path.basename(filepath))
    return m.group(1) if m else None


def _find_stem_file(files: list[str], stem_name: str) -> str | None:
    for f in files:
        if f"({stem_name})" in os.path.basename(f):
            return f
    return None
