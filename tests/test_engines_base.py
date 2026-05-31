"""Unit tests for audiolla.engines.base — EngineBase lifecycle, lock
discipline, idle-clock semantics. ML-library-free; the real engines'
``_load_sync`` is mocked here."""

from __future__ import annotations

import pytest

from audiolla.engines.base import EngineBase


# Use a real fake engine subclass that records load + release calls so the
# test can assert on the lifecycle transitions.

class _RecorderEngine(EngineBase):
    def __init__(self, slug: str = "rec", entry: dict | None = None) -> None:
        super().__init__(slug, entry or {})
        self.load_calls = 0
        self.release_calls = 0

    def _load_sync(self):
        self.load_calls += 1
        return object()  # any non-None sentinel — counts as "loaded"

    def _release_model(self, model) -> None:
        self.release_calls += 1


@pytest.fixture
def engine() -> _RecorderEngine:
    return _RecorderEngine()


# ── lifecycle ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_loaded_initially_false(engine: _RecorderEngine) -> None:
    assert engine.loaded() is False


@pytest.mark.asyncio
async def test_get_model_loads_once(engine: _RecorderEngine) -> None:
    m1 = await engine.get_model()
    m2 = await engine.get_model()
    assert m1 is m2
    assert engine.load_calls == 1
    assert engine.loaded() is True


@pytest.mark.asyncio
async def test_get_model_touches_idle_clock(engine: _RecorderEngine) -> None:
    # Before any call, last_used_secs_ago is None.
    assert engine.last_used_secs_ago() is None
    await engine.get_model()
    # After get_model, _touch has fired, so last_used_secs_ago is finite.
    secs = engine.last_used_secs_ago()
    assert secs is not None
    assert secs >= 0.0
    assert secs < 1.0


@pytest.mark.asyncio
async def test_unload_releases_and_clears(engine: _RecorderEngine) -> None:
    await engine.get_model()
    assert engine.loaded() is True
    await engine.unload()
    assert engine.loaded() is False
    assert engine.release_calls == 1
    assert engine.last_used_secs_ago() is None


@pytest.mark.asyncio
async def test_unload_noop_when_not_loaded(engine: _RecorderEngine) -> None:
    await engine.unload()  # never loaded
    assert engine.release_calls == 0


@pytest.mark.asyncio
async def test_unload_with_idle_ttl_skips_if_recently_touched(
    engine: _RecorderEngine,
) -> None:
    await engine.get_model()
    # Engine was just touched; idle ≈ 0s. Calling unload with ttl=60 should
    # observe idle < ttl under the lock and skip the release.
    await engine.unload(if_idle_for=60.0)
    assert engine.loaded() is True
    assert engine.release_calls == 0


@pytest.mark.asyncio
async def test_unload_with_idle_ttl_proceeds_if_stale(
    engine: _RecorderEngine,
) -> None:
    await engine.get_model()
    # Force the idle clock to be far in the past.
    import time
    engine._last_used = time.monotonic() - 1000
    await engine.unload(if_idle_for=10.0)
    assert engine.loaded() is False
    assert engine.release_calls == 1


# ── default _load_sync (no-weights engines) ──────────────────────────────────

@pytest.mark.asyncio
async def test_default_load_sync_returns_none() -> None:
    e = EngineBase("noweights", {})
    # The default _load_sync returns None — so loaded() stays False because
    # `self._model = None` doesn't transition the loaded() check from None.
    m = await e.get_model()
    assert m is None
    assert e.loaded() is False
