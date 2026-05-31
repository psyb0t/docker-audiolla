"""Generic effects-chain engine (pedalboard 0.9.20, GPL v3 — backend).

Exposes the full pedalboard effect catalog as an ordered chain. Users
supply a list of ``{type, params}`` objects and the engine instantiates
the matching pedalboard class with the given keyword arguments, then
applies the chain to the input audio.

The engine name is intentionally generic (``fx_chain`` not
``pedalboard_chain``) — the future-proof contract is "apply this list
of named effects in order", not "use pedalboard". A future executor
could route the same wire shape to a different DSP library if pedalboard
ever sprouts a license issue or a faster alternative shows up.

Supported effect types — every safe-by-construction pedalboard class
that operates on audio frames. Excludes anything that needs out-of-band
state (Bus, ExternalPlugin, VST3Plugin) — those need explicit
configuration and are not appropriate to expose to untrusted callers.

  Compressor, Limiter, NoiseGate, Gain, Clipping, Distortion,
  Bitcrush, Convolution, Reverb, MVerb, Chorus, Delay, Phaser,
  PitchShift, HighShelfFilter, LowShelfFilter, PeakFilter,
  HighpassFilter, LowpassFilter, LadderFilter, IIRFilter,
  GSMFullRateCompressor, MP3Compressor, Resample, Invert

Each effect's params are forwarded to the constructor as keyword
arguments. Unknown params raise; the user gets a clear error.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

from ..audio import AudioConversionError, encode_audio, to_wav_float32
from .base import EngineBase


# Allowlist of pedalboard classes that accept (samples, sample_rate) and
# don't require external state (plugins, file convolution kernels, etc.).
# Convolution IS included — it ships with built-in IRs and accepts a path
# only if the user supplies one; we forward params verbatim.
_ALLOWED_EFFECTS = frozenset({
    "Compressor", "Limiter", "NoiseGate", "Gain", "Clipping",
    "Distortion", "Bitcrush",
    "Reverb", "Chorus", "Delay", "Phaser", "PitchShift",
    "HighShelfFilter", "LowShelfFilter", "PeakFilter",
    "HighpassFilter", "LowpassFilter", "LadderFilter", "IIRFilter",
    "GSMFullRateCompressor", "MP3Compressor",
    "Resample", "Invert",
    # Convolution: requires `impulse_response_filename` kw — caller's
    # responsibility to supply a real path. We don't load arbitrary
    # filesystem paths beyond what pedalboard itself does.
    "Convolution",
})


class FxChainError(AudioConversionError):
    """Chain failed validation or pedalboard instantiation."""


class FxChainEngine(EngineBase):
    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)

    async def fx(
        self,
        raw: bytes,
        filename: str,
        *,
        effects: list[dict[str, Any]],
        output_format: str = "wav",
    ) -> bytes:
        if not isinstance(effects, list):
            raise FxChainError("effects must be a list of {type, params}")
        # Validate up-front so a malformed entry doesn't fire mid-render.
        for i, eff in enumerate(effects):
            if not isinstance(eff, dict):
                raise FxChainError(
                    f"effects[{i}] must be an object, got {type(eff).__name__}"
                )
            t = eff.get("type")
            if not isinstance(t, str) or t not in _ALLOWED_EFFECTS:
                raise FxChainError(
                    f"effects[{i}].type {t!r} is not allowed; "
                    f"valid: {sorted(_ALLOWED_EFFECTS)}"
                )
            params = eff.get("params", {})
            if not isinstance(params, dict):
                raise FxChainError(
                    f"effects[{i}].params must be an object, got "
                    f"{type(params).__name__}"
                )
        async with self._lock:
            result = await asyncio.to_thread(
                self._fx_sync, raw, filename, effects, output_format,
            )
            self._touch()
            return result

    def _fx_sync(
        self,
        raw: bytes,
        filename: str,
        effects: list[dict[str, Any]],
        output_format: str,
    ) -> bytes:
        import numpy as np
        import soundfile as sf

        wav_path = to_wav_float32(raw, filename)
        out_fd, out_wav = tempfile.mkstemp(prefix="audiolla-fx-", suffix=".wav")
        os.close(out_fd)

        try:
            audio, sr = sf.read(wav_path, always_2d=False, dtype="float32")
            if audio.ndim == 1:
                audio = np.stack([audio, audio], axis=-1)

            board = self._build_chain(effects)
            processed = board(audio, sample_rate=sr)
            np.clip(processed, -1.0, 1.0, out=processed)
            sf.write(out_wav, processed, sr, subtype="PCM_16")
            audio_bytes, _ct = encode_audio(out_wav, output_format)
            return audio_bytes
        finally:
            for p in (wav_path, out_wav):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    def _build_chain(self, effects: list[dict[str, Any]]) -> Any:
        import pedalboard

        plugins = []
        for i, eff in enumerate(effects):
            cls_name = eff["type"]
            cls = getattr(pedalboard, cls_name, None)
            if cls is None:
                raise FxChainError(
                    f"effects[{i}].type {cls_name!r} is not present in this "
                    "version of pedalboard"
                )
            params = eff.get("params", {})
            try:
                plugins.append(cls(**params))
            except TypeError as exc:
                # Wrong/extra kwargs — surface the pedalboard error verbatim
                # so the caller can see which param was bad.
                raise FxChainError(
                    f"effects[{i}] ({cls_name}): {exc}"
                ) from exc
            except Exception as exc:  # noqa: BLE001
                # ValueError for bad ranges, etc.
                raise FxChainError(
                    f"effects[{i}] ({cls_name}): {exc}"
                ) from exc
        return pedalboard.Pedalboard(plugins)
