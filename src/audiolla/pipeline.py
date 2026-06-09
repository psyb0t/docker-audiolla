"""Op-pipeline engine — run a list of audio transformations against a single
input file, server-side.

Pipelines are the engine that both ``/v1/pipeline`` (user-supplied chain)
and ``/v1/presets/{name}`` (curated server-side YAML) ride on top of.

Contract: every op takes ``(raw: bytes, filename: str, **params)`` and
returns ``bytes`` (the encoded audio for the next step). Ops that return
JSON-only analysis (``audio_info``, ``analyze``, ``loudness``, etc.) are
deliberately NOT in the registry — pipelines are byte-in, byte-out by
design. If you need analysis, call those endpoints standalone.

The registry maps op slugs to async callables. Adding a new op is a
single entry plus a thin wrapper that resolves the engine (if needed)
and forwards params.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from .audio import (
    AudioConversionError,
    convert_audio,
    deess,
    eq_audio,
    fade_audio,
    loop_audio,
    mid_side_decode,
    mid_side_encode,
    multiband_compress,
    pan_audio,
    repair_audio,
    reverse_audio,
    speed_audio,
    stereo_width_audio,
    transient_shape,
    trim_audio,
)
from .engines import (
    is_deepfilter_engine,
    is_fx_engine,
    is_loudness_engine,
    is_noise_reduce_engine,
    is_pitch_correct_engine,
    is_stretch_engine,
    is_thumbnail_engine,
    is_transform_engine,
    is_uvr_restore_engine,
)
import logging

_log = logging.getLogger("audiolla.pipeline")


class PipelineError(Exception):
    """A pipeline step failed validation, dispatch, or execution."""


def _require_engine(engines: dict, slug: str, check: Callable[[Any], bool], why: str) -> Any:
    eng = engines.get(slug)
    if eng is None or not check(eng):
        raise PipelineError(f"engine {slug!r} not configured / {why}")
    return eng


# ── ops ──────────────────────────────────────────────────────────────────────


async def _op_restore(engines: dict, raw: bytes, filename: str, *, engine: str,
                      aggressive: bool = False, output_format: str = "wav") -> bytes:
    eng = _require_engine(engines, engine, is_uvr_restore_engine, "no restore method")
    return await eng.restore(raw, filename, output_format=output_format, aggressive=aggressive)


async def _op_fx(engines: dict, raw: bytes, filename: str, *, effects: list,
                 output_format: str = "wav") -> bytes:
    eng = _require_engine(engines, "fx-chain", is_fx_engine, "fx-chain not present")
    return await eng.fx(raw, filename, effects=effects, output_format=output_format)


async def _op_transform(engines: dict, raw: bytes, filename: str, *,
                        operations: list, output_format: str = "wav") -> bytes:
    eng = _require_engine(engines, "sox-transform", is_transform_engine, "sox-transform not present")
    return await eng.transform(raw, filename, operations=operations, output_format=output_format)


async def _op_normalize(engines: dict, raw: bytes, filename: str, *,
                        target_lufs: float, output_format: str = "wav") -> bytes:
    eng = _require_engine(engines, "librosa-analyze", is_loudness_engine, "loudness measurement missing")
    audio_bytes, _measured = await eng.normalize_lufs(
        raw, filename, target_lufs=target_lufs, output_format=output_format,
    )
    return audio_bytes


async def _op_master(engines: dict, raw: bytes, filename: str, *, mode: str,
                     preset: str | None = None, target_lufs: float | None = None,
                     output_format: str = "wav", reference_raw: bytes | None = None,
                     reference_filename: str | None = None) -> bytes:
    if mode == "chain":
        eng = engines.get("pedalboard-chain")
        if eng is None or not hasattr(eng, "master_chain"):
            raise PipelineError("pedalboard-chain engine not configured for mode=chain")
        if not preset:
            raise PipelineError("master: mode=chain requires a preset name")
        return await eng.master_chain(raw, filename, preset=preset,
                                      target_lufs=target_lufs, output_format=output_format)
    if mode == "reference":
        eng = engines.get("matchering")
        if eng is None or not hasattr(eng, "master_reference"):
            raise PipelineError("matchering engine not configured for mode=reference")
        if reference_raw is None or reference_filename is None:
            raise PipelineError("master: mode=reference requires reference_raw + reference_filename")
        return await eng.master_reference(raw, filename, reference_raw, reference_filename,
                                          target_lufs=target_lufs, output_format=output_format)
    raise PipelineError(f"master: mode must be 'chain' or 'reference', got {mode!r}")


async def _op_enhance(engines: dict, raw: bytes, filename: str, *, engine: str = "deepfilter",
                      output_format: str = "wav") -> bytes:
    eng = _require_engine(engines, engine, is_deepfilter_engine, "no neural enhancement")
    return await eng.enhance(raw, filename, output_format=output_format)


async def _op_pitch_correct(engines: dict, raw: bytes, filename: str, *,
                            strength: float = 1.0, output_format: str = "wav") -> bytes:
    eng = next((e for e in engines.values() if is_pitch_correct_engine(e)), None)
    if eng is None:
        raise PipelineError("no pitch-correct engine configured")
    return await eng.pitch_correct(raw, filename, strength=strength, output_format=output_format)


async def _op_stretch(engines: dict, raw: bytes, filename: str, *,
                      tempo_factor: float = 1.0, pitch_semitones: float = 0.0,
                      output_format: str = "wav") -> bytes:
    eng = _require_engine(engines, "stretch", is_stretch_engine, "stretch engine missing")
    return await eng.stretch(raw, filename, tempo_factor=tempo_factor,
                             pitch_semitones=pitch_semitones, output_format=output_format)


async def _op_noise_reduce(engines: dict, raw: bytes, filename: str, *,
                           engine: str = "noise-reduce", stationary: bool = False,
                           prop_decrease: float = 1.0, output_format: str = "wav") -> bytes:
    eng = engines.get(engine)
    if eng is None:
        raise PipelineError(f"engine {engine!r} not configured")
    if is_noise_reduce_engine(eng):
        return await eng.reduce(raw, filename, stationary=stationary,
                                prop_decrease=prop_decrease, output_format=output_format)
    if is_uvr_restore_engine(eng):
        return await eng.restore(raw, filename, output_format=output_format)
    raise PipelineError(f"engine {engine!r} does not support noise reduction")


async def _op_thumbnail(engines: dict, raw: bytes, filename: str, *,
                        duration_sec: float = 30.0, output_format: str = "wav") -> bytes:
    eng = next((e for e in engines.values() if is_thumbnail_engine(e)), None)
    if eng is None:
        raise PipelineError("no thumbnail engine configured")
    audio_bytes, _meta = await eng.thumbnail(raw, filename, duration_sec=duration_sec,
                                             output_format=output_format)
    return audio_bytes


# ── audio.py wrappers (run in thread pool — they're synchronous DSP) ─────────


async def _op_trim(engines: dict, raw: bytes, filename: str, *,
                   start_sec: float = 0.0, end_sec: float, output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(trim_audio, raw, filename, start_sec, end_sec, output_format)


async def _op_speed(engines: dict, raw: bytes, filename: str, *, speed: float,
                    output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(speed_audio, raw, filename, speed, output_format)


async def _op_convert(engines: dict, raw: bytes, filename: str, *,
                      output_format: str = "wav", sample_rate: int | None = None,
                      channels: int | None = None) -> bytes:
    del engines
    return await asyncio.to_thread(convert_audio, raw, filename, output_format, sample_rate, channels)


async def _op_fade(engines: dict, raw: bytes, filename: str, *,
                   fade_in: float = 0.0, fade_out: float = 0.0,
                   curve: str = "tri", output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(fade_audio, raw, filename, output_format,
                                   fade_in=fade_in, fade_out=fade_out, curve=curve)


async def _op_reverse(engines: dict, raw: bytes, filename: str, *,
                      output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(reverse_audio, raw, filename, output_format)


async def _op_loop(engines: dict, raw: bytes, filename: str, *, count: int = 2,
                   output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(loop_audio, raw, filename, output_format, count)


async def _op_stereo_width(engines: dict, raw: bytes, filename: str, *,
                           width: float = 1.0, output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(stereo_width_audio, raw, filename, output_format, width)


async def _op_pan(engines: dict, raw: bytes, filename: str, *,
                  position: float = 0.0, output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(pan_audio, raw, filename, output_format, position)


async def _op_eq(engines: dict, raw: bytes, filename: str, *, bands: list,
                 output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(eq_audio, raw, filename, output_format, bands)


async def _op_mid_side(engines: dict, raw: bytes, filename: str, *,
                       mode: str, output_format: str = "wav") -> bytes:
    del engines
    if mode == "encode":
        return await asyncio.to_thread(mid_side_encode, raw, filename, output_format)
    if mode == "decode":
        return await asyncio.to_thread(mid_side_decode, raw, filename, output_format)
    raise PipelineError(f"mid_side: mode must be 'encode' or 'decode', got {mode!r}")


async def _op_repair(engines: dict, raw: bytes, filename: str, *,
                     declip: bool = True, dehum: bool = False, hum_freq: float = 50.0,
                     output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(repair_audio, raw, filename,
                                   declip=declip, dehum=dehum, hum_freq=hum_freq,
                                   output_format=output_format)


async def _op_transient(engines: dict, raw: bytes, filename: str, *,
                        attack_gain_db: float = 0.0, sustain_gain_db: float = 0.0,
                        output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(transient_shape, raw, filename,
                                   attack_gain_db=attack_gain_db,
                                   sustain_gain_db=sustain_gain_db,
                                   output_format=output_format)


async def _op_multiband_compress(engines: dict, raw: bytes, filename: str, *,
                                 crossovers_hz: list, bands: list,
                                 output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(multiband_compress, raw, filename,
                                   crossovers_hz=crossovers_hz, bands=bands,
                                   output_format=output_format)


async def _op_deess(engines: dict, raw: bytes, filename: str, *,
                    threshold_db: float = -20.0, frequency_hz: float = 6000.0,
                    ratio: float = 4.0, output_format: str = "wav") -> bytes:
    del engines
    return await asyncio.to_thread(deess, raw, filename, threshold_db=threshold_db,
                                   frequency_hz=frequency_hz, ratio=ratio,
                                   output_format=output_format)


# conv_reverb, mix, concat, sidechain_duck need extra inputs (IR, multiple
# tracks, trigger). They're not exposable as single-step pipeline ops without
# expanding the contract — skip from registry for now.


# ── registry ─────────────────────────────────────────────────────────────────


OpFn = Callable[..., Awaitable[bytes]]


OPS: dict[str, OpFn] = {
    # engine-backed
    "restore": _op_restore,
    "fx": _op_fx,
    "transform": _op_transform,
    "normalize": _op_normalize,
    "master": _op_master,
    "enhance": _op_enhance,
    "pitch_correct": _op_pitch_correct,
    "stretch": _op_stretch,
    "noise_reduce": _op_noise_reduce,
    "thumbnail": _op_thumbnail,
    # stateless DSP
    "trim": _op_trim,
    "speed": _op_speed,
    "convert": _op_convert,
    "fade": _op_fade,
    "reverse": _op_reverse,
    "loop": _op_loop,
    "stereo_width": _op_stereo_width,
    "pan": _op_pan,
    "eq": _op_eq,
    "mid_side": _op_mid_side,
    "repair": _op_repair,
    "transient": _op_transient,
    "multiband_compress": _op_multiband_compress,
    "deess": _op_deess,
}


def available_ops() -> list[str]:
    return sorted(OPS)


# ── runner ───────────────────────────────────────────────────────────────────


async def run_pipeline(
    engines: dict,
    raw: bytes,
    filename: str,
    steps: list[dict],
) -> tuple[bytes, list[dict]]:
    """Run a pipeline of ops against ``raw``. Returns ``(final_bytes, step_log)``
    where step_log is a list of ``{step, op, params, output_format, size}``
    entries for the response body.

    Each step must be a dict with ``op`` (registry key) and optional
    ``params`` (kwargs forwarded to the op). PipelineError bubbles up
    with a clear "step N: …" prefix; the caller maps it to HTTP 400.
    """
    if not isinstance(steps, list) or not steps:
        raise PipelineError("steps must be a non-empty list")

    _log.info("pipeline starting: %d step(s), input=%s bytes", len(steps), len(raw))
    step_log: list[dict] = []
    current = raw
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise PipelineError(f"step {i}: must be an object, got {type(step).__name__}")
        op_name = step.get("op")
        if not isinstance(op_name, str) or op_name not in OPS:
            raise PipelineError(
                f"step {i}: unknown op {op_name!r}; valid: {available_ops()}"
            )
        params = step.get("params", {})
        if not isinstance(params, dict):
            raise PipelineError(f"step {i} ({op_name}): params must be an object")
        fn = OPS[op_name]
        _log.debug("pipeline step %d: op=%s params=%s", i, op_name, params)
        try:
            current = await fn(engines, current, filename, **params)
        except PipelineError as exc:
            _log.warning("pipeline step %d (%s) failed: %s", i, op_name, exc)
            # The op already raised a PipelineError (e.g. missing engine).
            # Wrap it with the step index so the caller can pinpoint which
            # step in a long pipeline failed.
            raise PipelineError(f"step {i} ({op_name}): {exc}") from exc
        except AudioConversionError as exc:
            _log.warning("pipeline step %d (%s) AudioConversionError: %s", i, op_name, exc)
            raise PipelineError(f"step {i} ({op_name}): {exc}") from exc
        except TypeError as exc:
            _log.warning("pipeline step %d (%s) bad params: %s", i, op_name, exc)
            # Wrong kwargs — clarify the offending step
            raise PipelineError(f"step {i} ({op_name}): bad params: {exc}") from exc
        step_log.append({
            "step": i,
            "op": op_name,
            "params": params,
            "size_after": len(current),
        })

    _log.info("pipeline done: %d step(s), output=%d bytes", len(steps), len(current))
    return current, step_log
