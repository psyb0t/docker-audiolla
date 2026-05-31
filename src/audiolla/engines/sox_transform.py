"""pysox DSP transform chain engine (pysox 1.4.1, BSD-3-Clause).

Accepts an array of ``{op, params}`` objects. Ops map to SoX effects
applied in order via ``sox.Transformer``. Input decoded to a temp WAV
via ffmpeg first; output encoded to the requested format at egress.

Supported ops and their expected ``params`` keys (matching the OpenAPI
``TransformOperation.op`` enum):

  gain       — {db: float}                              → gain(gain_db=db)
  equalizer  — {frequency: float, width_q: float, gain_db: float}
                                                        → equalizer(...)
  compand    — {attack_time, decay_time, soft_knee_db,
                tf_points: [[in_db, out_db], ...]}     → compand(...)
  reverb     — {reverberance: int (0-100),
                pre_delay_ms: int, room_scale: int}    → reverb(...)
  pitch      — {n_semitones: float}                    → pitch(n_semitones)
                                                        (semitones, NOT cents)
  tempo      — {factor: float}                         → tempo(factor)
  rate       — {samplerate: int}                       → rate(samplerate)
  channels   — {n_channels: int}                       → channels(n_channels)
  trim       — {start_time: float, end_time?: float}   → trim(start, end)
  pad        — {start_duration: float, end_duration: float}
                                                        → pad(start, end)

No model weights — ``get_model()`` is a no-op. ``sox.Transformer.build_file``
is synchronous; the call wraps in ``asyncio.to_thread`` so the event loop
stays unblocked.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
from typing import Any

from ..audio import AudioConversionError, encode_audio, to_wav_float32
from .base import EngineBase


_OP_HANDLERS = {
    "gain": lambda tfm, p: tfm.gain(gain_db=float(p["db"])),
    "equalizer": lambda tfm, p: tfm.equalizer(
        frequency=float(p["frequency"]),
        width_q=float(p.get("width_q", 1.0)),
        gain_db=float(p["gain_db"]),
    ),
    "compand": lambda tfm, p: tfm.compand(
        attack_time=float(p.get("attack_time", 0.02)),
        decay_time=float(p.get("decay_time", 0.2)),
        soft_knee_db=float(p.get("soft_knee_db", 6.0)),
        tf_points=[tuple(pt) for pt in p.get(
            "tf_points",
            [(-70, -70), (-30, -30), (-20, -15), (0, -10)],
        )],
    ),
    "reverb": lambda tfm, p: tfm.reverb(
        reverberance=int(p.get("reverberance", 50)),
        pre_delay=int(p.get("pre_delay_ms", 0)),
        room_scale=int(p.get("room_scale", 100)),
    ),
    "pitch": lambda tfm, p: tfm.pitch(n_semitones=float(p["n_semitones"])),
    "tempo": lambda tfm, p: tfm.tempo(factor=float(p["factor"])),
    "rate": lambda tfm, p: tfm.rate(samplerate=int(p["samplerate"])),
    "channels": lambda tfm, p: tfm.channels(n_channels=int(p["n_channels"])),
    "trim": lambda tfm, p: tfm.trim(
        start_time=float(p["start_time"]),
        end_time=float(p["end_time"]) if p.get("end_time") is not None else None,
    ),
    "pad": lambda tfm, p: tfm.pad(
        start_duration=float(p.get("start_duration", 0.0)),
        end_duration=float(p.get("end_duration", 0.0)),
    ),
}


class SoxTransformEngine(EngineBase):
    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)

    async def transform(
        self,
        raw: bytes,
        filename: str,
        operations: list[dict[str, Any]],
        output_format: str = "wav",
    ) -> bytes:
        async with self._lock:
            result = await asyncio.to_thread(
                self._transform_sync, raw, filename, operations, output_format,
            )
            self._touch()
            return result

    def _transform_sync(
        self,
        raw: bytes,
        filename: str,
        operations: list[dict[str, Any]],
        output_format: str,
    ) -> bytes:
        import sox

        wav_in = to_wav_float32(raw, filename)
        out_fd, wav_out = tempfile.mkstemp(prefix="audiolla-sox-", suffix=".wav")
        os.close(out_fd)
        try:
            tfm = sox.Transformer()
            for idx, op_item in enumerate(operations):
                op_name = str(op_item.get("op") or "")
                params = op_item.get("params") or {}
                handler = _OP_HANDLERS.get(op_name)
                if handler is None:
                    raise AudioConversionError(
                        f"operation {idx}: unknown op {op_name!r}; "
                        f"valid: {sorted(_OP_HANDLERS)}"
                    )
                try:
                    handler(tfm, params)
                except (KeyError, ValueError, TypeError) as exc:
                    raise AudioConversionError(
                        f"operation {idx} ({op_name}): bad params {params!r}: {exc}"
                    ) from exc

            try:
                tfm.build_file(wav_in, wav_out)
            except Exception as exc:  # noqa: BLE001
                raise AudioConversionError(f"sox build_file failed: {exc}") from exc

            audio_bytes, _ct = encode_audio(wav_out, output_format)
            return audio_bytes
        finally:
            for p in (wav_in, wav_out):
                try:
                    os.unlink(p)
                except OSError:
                    pass
