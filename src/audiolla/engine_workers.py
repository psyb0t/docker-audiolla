from __future__ import annotations

import time
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from typing import Any

from fastapi import HTTPException

from audiolla.engines import build_engines
from audiolla.engines.base import EngineBase
from audiolla.model_process import ModelProcess


class AudioWorker:
    def __init__(self, slug: str, entry: dict, device: str) -> None:
        self.engine = build_engines({slug: entry}, device)[slug]

    async def execute(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        if operation == "prefetch":
            await self.engine.prefetch()
            return None
        if operation == "get_model":
            await self.engine.get_model()
            return None
        return await getattr(self.engine, operation)(*args, **kwargs)

    def resident(self) -> bool:
        return bool(self.engine.loaded())

    async def close(self) -> None:
        return None


class AudioWorkers:
    def __init__(self) -> None:
        self.active = 0
        self.unloading = False

    @contextmanager
    def inference(self) -> Iterator[None]:
        if self.unloading:
            raise HTTPException(status_code=409, detail="engines are being unloaded")
        self.active += 1
        try:
            yield
        finally:
            self.active -= 1

    @contextmanager
    def eviction(self) -> Iterator[None]:
        if self.active or self.unloading:
            raise HTTPException(status_code=409, detail="an audio engine is busy")
        self.unloading = True
        try:
            yield
        finally:
            self.unloading = False


class WorkerEngine:
    def __init__(self, engine: EngineBase, device: str, workers: AudioWorkers) -> None:
        self._engine = engine
        self._workers = workers
        self._last_used: float | None = None
        self._process = ModelProcess(AudioWorker, engine.slug, engine.entry, device)

    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(name)
        value = getattr(self._engine, name)
        return partial(self._call, name) if callable(value) else value

    async def _call(self, operation: str, *args: Any, **kwargs: Any) -> Any:
        with self._workers.inference():
            try:
                return await self._process.call(operation, *args, **kwargs)
            finally:
                self._last_used = time.monotonic()

    def loaded(self) -> bool:
        return bool(self._process.resident)

    def last_used_secs_ago(self) -> float | None:
        return None if self._last_used is None else time.monotonic() - self._last_used

    async def prefetch(self) -> None:
        await self._call("prefetch")

    async def unload(self, if_idle_for: float | None = None) -> None:
        if self._process.busy:
            return
        if if_idle_for is not None:
            idle = self.last_used_secs_ago()
            if idle is None or idle < if_idle_for:
                return
        await self.close()

    async def close(self) -> None:
        await self._process.stop()
        self._last_used = None


def isolate_models(
    engines: dict[str, Any], device: str, workers: AudioWorkers
) -> dict[str, Any]:
    return {
        slug: (
            WorkerEngine(engine, device, workers)
            if type(engine)._load_sync is not EngineBase._load_sync
            else engine
        )
        for slug, engine in engines.items()
    }
