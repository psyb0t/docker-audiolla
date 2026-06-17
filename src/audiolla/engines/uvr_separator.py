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


def _uvr_log_level() -> int:
    """Bridge the audio-separator library's own log level to LOG_LEVEL.

    audio-separator configures its own logger and won't honour the root
    handler's level by default. Forward LOG_LEVEL=DEBUG into the library
    so operators can debug the "model produced no output files" path
    without rebuilding. Falls back to WARNING in production to keep the
    library's numba spam out of the audiolla logs.
    """
    raw = (os.environ.get("LOG_LEVEL") or "").strip().upper()
    if raw == "WARN":
        raw = "WARNING"
    if raw in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        return getattr(logging, raw)
    return logging.WARNING


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
        # Do NOT pass output_single_stem here. The library's filter is a
        # case-insensitive match against the MODEL's own primary_stem
        # name (read from its YAML/ckpt config). Our engines.json names
        # ("No Reverb", "No Echo", "No Noise") rarely match the model's
        # configured stem name ("Vocals", "Other", etc.) — when they
        # don't, the library silently writes ZERO files and returns
        # output_files=[], surfacing as "model produced no output
        # files". Letting it write both stems and picking the right one
        # post-hoc is more robust.
        sep = Separator(
            model_file_dir=str(config.UVR_MODELS_DIR),
            output_format="WAV",
            log_level=_uvr_log_level(),
        )
        self._log.info("loading UVR model %s", self._model_filename)
        sep.load_model(self._model_filename)
        self._log.info("UVR model %s ready", self._model_filename)
        return sep

    def _load_aggressive_sync(self) -> object:
        from audio_separator.separator import Separator  # noqa: PLC0415

        os.makedirs(config.UVR_MODELS_DIR, exist_ok=True)
        # See _load_sync above for why output_single_stem is omitted.
        sep = Separator(
            model_file_dir=str(config.UVR_MODELS_DIR),
            output_format="WAV",
            log_level=_uvr_log_level(),
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

            # audio-separator snapshots output_dir into its per-arch
            # model_instance config at `load_model()` time. Mutating
            # sep.output_dir alone does NOT propagate to the model
            # instance that actually writes the file — pydub then exports
            # to cwd (usually /app/, root-owned) and the file lands in a
            # spot the runtime user can't read. Fix: set both.
            sep.output_dir = tmpdir
            if getattr(sep, "model_instance", None) is not None:
                sep.model_instance.output_dir = tmpdir
            output_files: list[str] = sep.separate(in_path)
            self._log.info(
                "restore separate done: output_files=%s tmpdir=%s",
                output_files, sorted(os.listdir(tmpdir)),
            )

            # audio-separator claims success and returns a filename even
            # when the model produced silence (nothing to extract from a
            # synthetic sine, e.g.). Filter to files that actually exist
            # on disk under tmpdir.
            existing = [
                fn for fn in output_files
                if os.path.exists(
                    fn if os.path.isabs(fn)
                    else os.path.join(tmpdir, os.path.basename(fn))
                )
            ]
            if not existing:
                # Recursive tmpdir listing so operators can diagnose
                # "audio-separator claimed an output file but didn't
                # write it" — usually means the model output was
                # silent / all zeros and the library dropped it. The
                # log line carries both what the library SAID it wrote
                # and what's actually on disk.
                _on_disk: list[str] = []
                for root, _, files in os.walk(tmpdir):
                    for f in files:
                        _on_disk.append(os.path.relpath(
                            os.path.join(root, f), tmpdir,
                        ))
                self._log.warning(
                    "phantom output: library reported %s; tmpdir tree=%s",
                    output_files, _on_disk,
                )
                raise UVRSeparatorError(
                    "model produced no output files"
                )

            target = existing[0]
            if self._primary_stem and len(existing) > 1:
                match = _find_stem_file(existing, self._primary_stem)
                if match:
                    target = match
            base = os.path.basename(target)
            candidate = os.path.join(tmpdir, base)
            target = candidate if os.path.exists(candidate) else target
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

            # See _restore_sync_with_sep — must mutate the per-arch
            # model_instance.output_dir too, not just the outer
            # Separator. Otherwise pydub exports to cwd (/app, root-
            # owned) and the file lands somewhere the runtime user
            # can't read.
            self._model.output_dir = tmpdir
            if getattr(self._model, "model_instance", None) is not None:
                self._model.model_instance.output_dir = tmpdir
            output_files: list[str] = self._model.separate(in_path)
            self._log.info(
                "separate done: output_files=%s tmpdir=%s",
                output_files, sorted(os.listdir(tmpdir)),
            )

            if not output_files:
                raise UVRSeparatorError(
                    f"model {self._model_filename!r} produced no output files"
                )

            result: dict[str, bytes] = {}
            for f in output_files:
                # Same dance as _restore_sync_with_sep — audio-separator
                # claims successful output for files it never actually
                # wrote (silence / no-content cases on synthetic input),
                # so re-resolve against tmpdir and skip if the file
                # doesn't actually exist there.
                base = os.path.basename(f)
                candidate = os.path.join(tmpdir, base)
                if os.path.exists(candidate):
                    abs_path = candidate
                elif os.path.isabs(f) and os.path.exists(f):
                    abs_path = f
                else:
                    continue  # phantom output — model claimed it but didn't write
                stem_name = _extract_stem_name(abs_path)
                if stem_name is None:
                    continue
                if stems and stem_name not in stems:
                    continue
                audio_bytes, _ = encode_audio(abs_path, output_format)
                result[stem_name] = audio_bytes

            if not result:
                raise UVRSeparatorError(
                    f"model {self._model_filename!r} produced no recognisable stems; "
                    f"files: {output_files}"
                )
            return result


# Newer audio-separator releases append the model filename after the
# stem tag: ``name_(Vocals)_model_bs_roformer_ep_317_sdr_12.wav`` instead
# of the older ``name_(Vocals).wav``. Match any parenthesised tag in the
# basename and take the LAST one — the stem name is always the trailing
# parenthesised group before any suffix.
_STEM_RE = re.compile(r"\(([^()]+)\)")


def _extract_stem_name(filepath: str) -> str | None:
    matches = _STEM_RE.findall(os.path.basename(filepath))
    return matches[-1] if matches else None


def _find_stem_file(files: list[str], stem_name: str) -> str | None:
    for f in files:
        if f"({stem_name})" in os.path.basename(f):
            return f
    return None
