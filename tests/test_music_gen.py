"""Unit tests for the text-to-music engine validators + wiring.

These DO NOT test generation. Real model output is verified end-to-end by
``tests/integration/e2e_generate.sh`` against the CUDA image (it generates
audio and re-runs it through ``/v1/audio/beats`` to prove the audio is
actually musical, not silence).

What this file checks is pre-model-load contract that runs on every call:

  - duck-type predicate (``is_music_gen_engine``) accepts every engine class
  - per-engine constants (SAMPLE_RATE, MAX_DURATION_SEC) match their model
  - the duration validator's boundary cases (zero / negative / above-cap /
    at-cap / below-cap) fire correctly
  - generate() rejects empty prompts + over-cap durations BEFORE touching
    GPU memory — so the user gets a fast 400 instead of a model load
  - the lyrics kwarg is accepted for API uniformity (every engine is
    instrumental and ignores it)
  - the MusicGen CC-BY-NC licence gate refuses to load the model unless
    ``AUDIOLLA_ENABLE_NONCOMMERCIAL=1`` is set
"""

from __future__ import annotations

import pytest

from audiolla.engines import is_music_gen_engine
from audiolla.engines.music_gen import (
    AudioLDM2Engine,
    MusicGenError,
    MusicGenMediumEngine,
    MusicGenSmallEngine,
    RiffusionEngine,
    StableAudioOpenEngine,
    _require_noncommercial_optin,
    _validate_duration,
)


# ── duck-type predicate ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "engine_cls,slug",
    [
        (StableAudioOpenEngine, "stable-audio-open"),
        (MusicGenSmallEngine, "musicgen-small"),
        (MusicGenMediumEngine, "musicgen-medium"),
        (RiffusionEngine, "riffusion"),
        (AudioLDM2Engine, "audioldm2"),
    ],
)
def test_is_music_gen_engine_accepts(engine_cls, slug):
    assert is_music_gen_engine(engine_cls(slug=slug, entry={}))


def test_is_music_gen_engine_rejects_unrelated():
    class _Empty:
        pass
    assert not is_music_gen_engine(_Empty())


# ── per-engine constants ────────────────────────────────────────────────────


def test_stable_audio_constants():
    assert StableAudioOpenEngine.SAMPLE_RATE == 44100
    assert StableAudioOpenEngine.MAX_DURATION_SEC == 47.0


def test_musicgen_small_constants():
    assert MusicGenSmallEngine.SAMPLE_RATE == 32000
    assert MusicGenSmallEngine.MAX_DURATION_SEC == 30.0
    assert MusicGenSmallEngine.MODEL_ID == "facebook/musicgen-small"


def test_musicgen_medium_constants():
    assert MusicGenMediumEngine.SAMPLE_RATE == 32000
    assert MusicGenMediumEngine.MAX_DURATION_SEC == 30.0
    assert MusicGenMediumEngine.MODEL_ID == "facebook/musicgen-medium"


def test_riffusion_constants():
    assert RiffusionEngine.SAMPLE_RATE == 22050
    assert RiffusionEngine.MAX_DURATION_SEC == 30.0
    assert RiffusionEngine.MODEL_ID == "riffusion/riffusion-model-v1"


def test_audioldm2_constants():
    assert AudioLDM2Engine.SAMPLE_RATE == 16000
    assert AudioLDM2Engine.MAX_DURATION_SEC == 30.0
    assert AudioLDM2Engine.MODEL_ID == "cvssp/audioldm2"


# ── duration validator ──────────────────────────────────────────────────────


def test_validate_duration_rejects_zero():
    with pytest.raises(MusicGenError, match="must be > 0"):
        _validate_duration(0.0, max_sec=60.0, engine="test")


def test_validate_duration_rejects_negative():
    with pytest.raises(MusicGenError, match="must be > 0"):
        _validate_duration(-5.0, max_sec=60.0, engine="test")


def test_validate_duration_rejects_above_cap():
    with pytest.raises(MusicGenError, match="exceeds engine cap"):
        _validate_duration(100.0, max_sec=60.0, engine="test")


def test_validate_duration_accepts_at_cap():
    _validate_duration(60.0, max_sec=60.0, engine="test")


def test_validate_duration_accepts_below_cap():
    _validate_duration(30.0, max_sec=60.0, engine="test")


# ── engine generate() input validation (no model load) ──────────────────────
#
# generate() validates prompt + duration BEFORE calling get_model(), so we
# can hit the bad-input branches without the model weights ever loading.


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "engine_cls,slug",
    [
        (StableAudioOpenEngine, "stable-audio-open"),
        (MusicGenSmallEngine, "musicgen-small"),
        (MusicGenMediumEngine, "musicgen-medium"),
        (RiffusionEngine, "riffusion"),
        (AudioLDM2Engine, "audioldm2"),
    ],
)
async def test_generate_rejects_empty_prompt(engine_cls, slug):
    eng = engine_cls(slug=slug, entry={})
    with pytest.raises(MusicGenError, match="prompt must be a non-empty string"):
        await eng.generate("", duration_sec=5.0)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "engine_cls,slug,over_cap",
    [
        (StableAudioOpenEngine, "stable-audio-open", 100.0),
        (MusicGenSmallEngine, "musicgen-small", 60.0),
        (MusicGenMediumEngine, "musicgen-medium", 60.0),
        (RiffusionEngine, "riffusion", 100.0),
        (AudioLDM2Engine, "audioldm2", 60.0),
    ],
)
async def test_generate_rejects_over_cap_duration(engine_cls, slug, over_cap):
    eng = engine_cls(slug=slug, entry={})
    with pytest.raises(MusicGenError, match="exceeds engine cap"):
        await eng.generate("drum loop", duration_sec=over_cap)


@pytest.mark.asyncio
async def test_stable_audio_ignores_lyrics():
    """stable-audio-open accepts a `lyrics` kwarg only for API uniformity
    (REST endpoint forwards it to every engine); the engine itself has no
    vocal stack, so the value is silently dropped — but the call must NOT
    blow up on validation."""
    eng = StableAudioOpenEngine(slug="stable-audio-open", entry={})
    # Hit the duration validator BEFORE the model load. The lyrics kwarg
    # is accepted; the over-cap duration triggers the early raise.
    with pytest.raises(MusicGenError, match="exceeds engine cap"):
        await eng.generate("ambient pad", duration_sec=999.0, lyrics="ignored")


# ── MusicGen CC-BY-NC licence gate ──────────────────────────────────────────


def test_licence_gate_raises_without_optin(monkeypatch):
    monkeypatch.delenv("AUDIOLLA_ENABLE_NONCOMMERCIAL", raising=False)
    with pytest.raises(MusicGenError, match="AUDIOLLA_ENABLE_NONCOMMERCIAL"):
        _require_noncommercial_optin("musicgen-small")


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "", "maybe"])
def test_licence_gate_rejects_falsey_values(monkeypatch, value):
    monkeypatch.setenv("AUDIOLLA_ENABLE_NONCOMMERCIAL", value)
    with pytest.raises(MusicGenError, match="AUDIOLLA_ENABLE_NONCOMMERCIAL"):
        _require_noncommercial_optin("musicgen-small")


@pytest.mark.parametrize("value", ["1", "true", "yes", "on", "TRUE", "Yes", "On"])
def test_licence_gate_accepts_truthy_values(monkeypatch, value):
    monkeypatch.setenv("AUDIOLLA_ENABLE_NONCOMMERCIAL", value)
    _require_noncommercial_optin("musicgen-small")


def test_licence_gate_message_links_to_licence(monkeypatch):
    monkeypatch.delenv("AUDIOLLA_ENABLE_NONCOMMERCIAL", raising=False)
    with pytest.raises(MusicGenError) as excinfo:
        _require_noncommercial_optin("musicgen-medium")
    msg = str(excinfo.value)
    assert "musicgen-medium" in msg
    assert "CC-BY-NC" in msg
    assert "https://" in msg  # licence link present


# ── AudioLDM2 has NO licence gate (CC-BY 4.0 — commercial-OK) ───────────────
#
# Sanity-check that AudioLDM2Engine._load_sync does NOT call the noncommercial
# opt-in helper. Stubs in torch + diffusers so the load path can be inspected
# without the heavy deps actually being installed for the unit test pass.


def test_audioldm2_does_not_invoke_licence_gate(monkeypatch):
    """Loading AudioLDM2 must NOT call _require_noncommercial_optin —
    CC-BY 4.0 weights allow commercial use, no opt-in required."""
    monkeypatch.delenv("AUDIOLLA_ENABLE_NONCOMMERCIAL", raising=False)
    called = {"n": 0}

    def _spy(_slug):
        called["n"] += 1

    monkeypatch.setattr(
        "audiolla.engines.music_gen._require_noncommercial_optin", _spy,
    )
    eng = AudioLDM2Engine(slug="audioldm2", entry={})
    # Don't actually load the model — just inspect the source code path
    # would need to traverse. The presence/absence of the helper call in
    # _load_sync is what matters; we monkey-patch + assert call count.
    import inspect
    src = inspect.getsource(eng._load_sync)
    assert "_require_noncommercial_optin" not in src, (
        "AudioLDM2Engine._load_sync must not gate on AUDIOLLA_ENABLE_NONCOMMERCIAL"
    )
    assert called["n"] == 0
