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
from typing import Any

from .. import config
from ..audio import AudioConversionError, encode_audio
from .base import EngineBase


class UVRSeparatorError(AudioConversionError):
    """Model inference failed or returned unexpected output."""


class UVRSeparatorEngine(EngineBase):
    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)
        self._model_filename: str = entry["model"]
        self._model_aggressive_filename: str | None = entry.get("model_aggressive")
        self._primary_stem: str | None = entry.get("primary_stem")
        self._aggressive_sep: Any = None
        self._aggressive_load_lock: asyncio.Lock = asyncio.Lock()
        self._aggressive_run_lock: asyncio.Lock = asyncio.Lock()

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

    def _load_aggressive_sync(self) -> object:
        from audio_separator.separator import Separator  # noqa: PLC0415

        os.makedirs(config.UVR_MODELS_DIR, exist_ok=True)
        sep = Separator(
            model_file_dir=str(config.UVR_MODELS_DIR),
            output_format="WAV",
            output_single_stem=self._primary_stem,
            log_level=logging.WARNING,
        )
        self._log.info("loading UVR aggressive model %s", self._model_aggressive_filename)
        sep.load_model(self._model_aggressive_filename)
        self._log.info("UVR aggressive model %s ready", self._model_aggressive_filename)
        return sep

    async def _get_aggressive_model(self) -> Any:
        self._touch()
        if self._aggressive_sep is not None:
            return self._aggressive_sep
        async with self._aggressive_load_lock:
            if self._aggressive_sep is not None:
                return self._aggressive_sep
            self._aggressive_sep = await asyncio.to_thread(self._load_aggressive_sync)
            self._touch()
        return self._aggressive_sep

    async def restore(
        self,
        raw: bytes,
        filename: str,
        *,
        output_format: str = "wav",
        aggressive: bool = False,
    ) -> bytes:
        """Run a restoration model. Returns primary (cleaned) stem bytes.

        When aggressive=True, uses the model_aggressive variant (if configured).
        """
        if aggressive:
            if not self._model_aggressive_filename:
                raise UVRSeparatorError(
                    f"engine {self.slug!r} has no aggressive model configured"
                )
            sep = await self._get_aggressive_model()
            run_lock = self._aggressive_run_lock
        else:
            sep = await self.get_model()
            run_lock = self._lock

        async with run_lock:
            result = await asyncio.to_thread(
                self._restore_sync_with_sep,
                sep,
                raw,
                filename,
                output_format,
            )
            self._touch()
            return result

    def _restore_sync_with_sep(
        self, sep: Any, raw: bytes, filename: str, output_format: str
    ) -> bytes:
        with tempfile.TemporaryDirectory(prefix="audiolla-uvr-") as tmpdir:
            in_path = os.path.join(tmpdir, filename)
            with open(in_path, "wb") as fh:
                fh.write(raw)

            sep.output_dir = tmpdir
            output_files: list[str] = sep.separate(in_path)

            if not output_files:
                raise UVRSeparatorError(
                    f"model produced no output files"
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
