"""Unit tests for FxChainEngine validation.

The actual pedalboard processing (.fx()) needs pedalboard + numpy +
soundfile installed — those live only in the prod image, not the dev
image. So these tests cover the upstream validation (allowed effect
allowlist, well-formed chain shape) without booting the DSP.

End-to-end audio output is covered by the integration suite."""

from __future__ import annotations

import pytest

from audiolla.engines.fx_chain import (
    FxChainEngine,
    FxChainError,
    _ALLOWED_EFFECTS,
)


def _engine() -> FxChainEngine:
    return FxChainEngine(slug="fx-chain", entry={"executor": "fx_chain"})


@pytest.mark.asyncio
async def test_fx_rejects_non_list_effects():
    with pytest.raises(FxChainError, match="must be a list"):
        await _engine().fx(b"x", "x.wav", effects={"type": "Gain"})  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_fx_rejects_non_object_effect_entry():
    with pytest.raises(FxChainError, match=r"effects\[0\] must be an object"):
        await _engine().fx(b"x", "x.wav", effects=["Compressor"])  # type: ignore[list-item]


@pytest.mark.asyncio
async def test_fx_rejects_missing_type():
    with pytest.raises(FxChainError, match=r"effects\[0\]\.type"):
        await _engine().fx(b"x", "x.wav", effects=[{"params": {}}])


@pytest.mark.asyncio
async def test_fx_rejects_unknown_type():
    with pytest.raises(FxChainError, match="not allowed"):
        await _engine().fx(
            b"x", "x.wav",
            effects=[{"type": "NotARealPedalboardClass"}],
        )


@pytest.mark.asyncio
async def test_fx_rejects_non_object_params():
    with pytest.raises(FxChainError, match="params must be an object"):
        await _engine().fx(
            b"x", "x.wav",
            effects=[{"type": "Gain", "params": [1, 2]}],
        )


@pytest.mark.asyncio
async def test_fx_allowlist_contains_common_effects():
    """Sanity check that the allowlist isn't accidentally empty or
    missing the workhorses."""
    for name in (
        "Compressor", "Limiter", "Reverb", "Chorus", "Delay",
        "PitchShift", "HighShelfFilter", "LowpassFilter",
    ):
        assert name in _ALLOWED_EFFECTS, f"{name} unexpectedly absent from allowlist"


@pytest.mark.asyncio
async def test_fx_allowlist_excludes_dangerous_classes():
    """Anything that lets the caller load arbitrary native code or
    point at random filesystem paths must NOT be exposed."""
    for name in ("VST3Plugin", "AudioUnitPlugin", "ExternalPlugin"):
        assert name not in _ALLOWED_EFFECTS, (
            f"{name} should NOT be in the allowlist — it loads native code"
        )
