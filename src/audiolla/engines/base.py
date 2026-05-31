"""Engine protocol — uniform lifecycle + per-capability method signatures.

All engines share lazy-load + idle-unload semantics:
  loaded()              — True if model weights are resident in memory
  get_model()           — load and return the model (cached after first call)
  unload()              — release weights, free GPU/RAM
  last_used_secs_ago()  — seconds since last active call; None if never used

Engines without ML weights (librosa, sox, pedalboard, matchering) never
actually load anything — their get_model() is a no-op and loaded() is always
False. The sweeper and eviction logic in server.py still calls them uniformly;
they just return quickly.

Per-capability method signatures (implemented by each backend):

  Separation (demucs):
    separate(raw, filename, stems) -> dict[stem_name, audio_bytes]

  Mastering (matchering):
    master_reference(raw, filename, ref_raw, ref_filename, *, target_lufs, output_format)
      -> audio_bytes

  Mastering (pedalboard-chain):
    master_chain(raw, filename, *, preset, target_lufs, output_format)
      -> audio_bytes

  Analysis (librosa):
    analyze(raw, filename, features) -> dict

  Analysis + loudness normalization (librosa):
    measure_lufs(raw, filename) -> float
    normalize_lufs(raw, filename, *, target_lufs, output_format) -> (audio_bytes, measured_lufs)

  Transform (sox):
    transform(raw, filename, operations, output_format) -> audio_bytes
"""

from __future__ import annotations

import asyncio
import gc
import logging
import time
from typing import Any


class EngineBase:
    """Shared lifecycle implementation for all engines.

    Engines with ML weights (DemucsEngine) override _load_sync().
    Engines without weights (librosa, sox, matchering, pedalboard) inherit
    the no-op implementation — get_model() returns None immediately.
    """

    def __init__(self, slug: str, entry: dict) -> None:
        self.slug = slug
        self.entry = entry
        self._lock = asyncio.Lock()
        self._model: Any = None
        self._last_used: float | None = None
        self._log = logging.getLogger(f"audiolla.engine.{slug}")

    def loaded(self) -> bool:
        return self._model is not None

    def last_used_secs_ago(self) -> float | None:
        if self._last_used is None:
            return None
        return time.monotonic() - self._last_used

    def _touch(self) -> None:
        self._last_used = time.monotonic()

    async def get_model(self) -> Any:
        # Reset the idle clock as early as possible so the sweeper cannot
        # decide to unload an engine mid-call between get_model and the
        # subsequent inference lock acquisition (the TOCTOU window).
        self._touch()
        if self._model is not None:
            return self._model
        async with self._lock:
            if self._model is not None:
                return self._model
            model = await asyncio.to_thread(self._load_sync)
            self._model = model
            self._touch()
            return model

    def _load_sync(self) -> Any:
        return None

    async def unload(self, if_idle_for: float | None = None) -> None:
        """Release the engine's resident model.

        ``if_idle_for`` is the sweeper's TTL — re-check the idle clock
        under the lock so we don't evict an engine that was touched
        between the sweeper's outside-the-lock observation and our
        acquisition. ``None`` means "unconditional unload" (manual
        `/unload` calls, sibling eviction).
        """
        async with self._lock:
            if self._model is None:
                return
            if if_idle_for is not None:
                idle = self.last_used_secs_ago()
                if idle is None or idle < if_idle_for:
                    return
            self._log.info("unloading %s", self.slug)
            model = self._model
            self._model = None
            self._last_used = None
        self._release_model(model)
        gc.collect()
        gc.collect()
        self._cuda_cleanup()
        self._log.info("unloaded %s", self.slug)

    def _release_model(self, model: Any) -> None:
        """Override to release ML model resources (e.g. model.cpu() + del)."""

    def _cuda_cleanup(self) -> None:
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.synchronize()
                torch.cuda.empty_cache()
                torch.cuda.ipc_collect()
        except ImportError:
            pass
