from __future__ import annotations

import asyncio
import logging

from . import config
from .engine_workers import AudioWorkers, WorkerEngine, isolate_models
from .engines import build_engines
from .logging import configure

log = logging.getLogger(__name__)


async def prefetch_models() -> None:
    registry = config.load_registry()
    workers = isolate_models(build_engines(registry, "cpu"), "cpu", AudioWorkers())
    for slug, engine in workers.items():
        if not isinstance(engine, WorkerEngine):
            continue
        try:
            await engine.prefetch()
        except Exception:  # noqa: BLE001
            # An unavailable engine can retry when requested after startup.
            log.exception("startup model download failed", extra={"engine": slug})
        finally:
            await engine.close()


if __name__ == "__main__":
    configure()
    asyncio.run(prefetch_models())
