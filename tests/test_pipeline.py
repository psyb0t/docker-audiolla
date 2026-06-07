"""Unit tests for audiolla.pipeline — registry shape + validation paths.

The actual op execution requires the full audio/engine stack (ffmpeg,
numpy, scipy, pedalboard, the engines) so it's covered by the
integration suite. These tests exercise the validation + dispatch logic
that runs before any heavy work.
"""

from __future__ import annotations

import pytest

from audiolla.pipeline import (
    OPS,
    PipelineError,
    available_ops,
    run_pipeline,
)


# ── registry shape ───────────────────────────────────────────────────────────


def test_ops_registry_has_core_audio_transforms():
    """Spot-check that the most-used ops are registered."""
    for op in ("restore", "fx", "normalize", "trim", "multiband_compress",
               "deess", "stretch", "transient", "eq"):
        assert op in OPS, f"missing core op: {op}"


def test_available_ops_returns_sorted_list():
    ops = available_ops()
    assert ops == sorted(ops)
    assert all(isinstance(o, str) for o in ops)
    assert len(ops) == len(OPS)


# ── run_pipeline validation ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_pipeline_rejects_empty_steps():
    with pytest.raises(PipelineError, match="non-empty list"):
        await run_pipeline(engines={}, raw=b"x", filename="a.wav", steps=[])


@pytest.mark.asyncio
async def test_pipeline_rejects_non_list_steps():
    with pytest.raises(PipelineError, match="non-empty list"):
        await run_pipeline(engines={}, raw=b"x", filename="a.wav", steps="not-a-list")  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_pipeline_rejects_step_not_an_object():
    with pytest.raises(PipelineError, match=r"step 0: must be an object"):
        await run_pipeline(engines={}, raw=b"x", filename="a.wav", steps=["bad"])


@pytest.mark.asyncio
async def test_pipeline_rejects_unknown_op():
    with pytest.raises(PipelineError, match=r"step 0: unknown op 'nonsense'"):
        await run_pipeline(
            engines={}, raw=b"x", filename="a.wav",
            steps=[{"op": "nonsense"}],
        )


@pytest.mark.asyncio
async def test_pipeline_rejects_missing_op_key():
    with pytest.raises(PipelineError, match=r"step 0: unknown op None"):
        await run_pipeline(
            engines={}, raw=b"x", filename="a.wav",
            steps=[{"params": {}}],
        )


@pytest.mark.asyncio
async def test_pipeline_rejects_non_dict_params():
    with pytest.raises(PipelineError, match=r"step 0 \(trim\): params must be an object"):
        await run_pipeline(
            engines={}, raw=b"x", filename="a.wav",
            steps=[{"op": "trim", "params": "not-a-dict"}],
        )


@pytest.mark.asyncio
async def test_pipeline_engine_op_reports_missing_engine():
    # restore op needs a uvr restore engine — we pass an empty engines dict.
    # The runner wraps the op-raised PipelineError with "step N (op):" prefix
    # so the caller can pinpoint the failing step.
    with pytest.raises(
        PipelineError,
        match=r"step 0 \(restore\): engine 'uvr-dereverb' not configured",
    ):
        await run_pipeline(
            engines={}, raw=b"x", filename="a.wav",
            steps=[{"op": "restore", "params": {"engine": "uvr-dereverb"}}],
        )


@pytest.mark.asyncio
async def test_pipeline_propagates_clear_step_index(monkeypatch):
    """A failure at step N must include 'step N' in the error so the caller
    can see exactly which step blew up in a long pipeline. We monkeypatch a
    no-op into OPS so steps 0 and 1 succeed without needing ffmpeg, then
    rely on the unknown-engine failure at step 2."""
    async def _noop(_engines, raw, _filename, **_params):
        return raw

    monkeypatch.setitem(OPS, "_test_noop", _noop)

    with pytest.raises(PipelineError, match=r"^step 2 \("):
        await run_pipeline(
            engines={}, raw=b"x", filename="a.wav",
            steps=[
                {"op": "_test_noop", "params": {}},
                {"op": "_test_noop", "params": {}},
                {"op": "restore", "params": {"engine": "uvr-dereverb"}},
            ],
        )
