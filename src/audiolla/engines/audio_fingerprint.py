"""Audio fingerprint engine — Chromaprint via ``fpcalc`` subprocess.

Computes a Chromaprint acoustic fingerprint of the input audio. The
fingerprint identifies a recording independently of encoding, bitrate,
and minor processing — useful for "is this the same song?" lookups and
duplicate detection.

The ``fpcalc`` binary ships with the ``libchromaprint-tools`` Debian
package, present in every prod image (LGPL-2.1). No model weights.

Output shape::

    {
      "duration": 215.34,            # seconds, as reported by fpcalc
      "fingerprint": "AQADtEqRRIuQ...",   # base64 packed Chromaprint
      "fingerprint_raw": [12, 35, ...]    # only if return_raw=true
    }
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import time

from ..audio import AudioConversionError, to_wav_float32
from .base import EngineBase


class FingerprintError(AudioConversionError):
    """fpcalc was missing or returned non-zero."""


class AudioFingerprintEngine(EngineBase):
    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)

    async def compute(
        self,
        raw: bytes,
        filename: str,
        *,
        analyze_seconds: float = 120.0,
        return_raw: bool = False,
    ) -> dict:
        """Run fpcalc over the audio. ``analyze_seconds`` caps how much
        of the input is fed to the fingerprinter — Chromaprint's standard
        is 120s (matches AcoustID's recommended length). Pass ``0`` to
        process the whole file.

        ``return_raw=True`` adds the unpacked integer-array fingerprint
        to the response (much larger than the base64 string).
        """
        if analyze_seconds < 0:
            self._log.warning(
                "rejecting fingerprint request: analyze_seconds=%s must be >= 0",
                analyze_seconds,
            )
            raise FingerprintError(
                f"analyze_seconds must be >= 0, got {analyze_seconds}"
            )
        self._log.info(
            "fingerprint start: filename=%s input_bytes=%d analyze_seconds=%s return_raw=%s",
            filename, len(raw), analyze_seconds, return_raw,
        )
        t0 = time.perf_counter()
        async with self._lock:
            result = await asyncio.to_thread(
                self._compute_sync, raw, filename, analyze_seconds, return_raw,
            )
            self._touch()
            dt = time.perf_counter() - t0
            self._log.info(
                "fingerprint done: filename=%s duration_ms=%.1f fp_len=%d raw_len=%d audio_duration=%.2f",
                filename, dt * 1000.0,
                len(result.get("fingerprint", "")),
                len(result.get("fingerprint_raw", []) or []),
                float(result.get("duration", 0.0)),
            )
            return result

    def _compute_sync(
        self,
        raw: bytes,
        filename: str,
        analyze_seconds: float,
        return_raw: bool,
    ) -> dict:
        wav_path = to_wav_float32(raw, filename)
        try:
            cmd = ["fpcalc", "-json"]
            if analyze_seconds > 0:
                cmd += ["-length", str(int(analyze_seconds))]
            cmd.append(wav_path)
            try:
                proc = subprocess.run(
                    cmd, check=False, capture_output=True, text=True,
                    timeout=300,
                )
            except FileNotFoundError as exc:
                self._log.exception("fpcalc binary not found on PATH")
                raise FingerprintError(
                    "fpcalc binary not found on PATH — is this the prod "
                    "image? (libchromaprint-tools provides it.)"
                ) from exc
            # fpcalc exit=3 means it hit EOF while decoding the last frame —
            # it still emits a valid fingerprint. Only hard-fail when stdout
            # is empty or unparseable.
            try:
                payload = json.loads(proc.stdout)
            except json.JSONDecodeError:
                if proc.returncode != 0:
                    tail = (proc.stderr or "").strip().splitlines()[-1:] or ["<no stderr>"]
                    self._log.warning(
                        "fpcalc exit=%d filename=%s stderr_tail=%s",
                        proc.returncode, filename, tail[0],
                    )
                    raise FingerprintError(
                        f"fpcalc exit={proc.returncode}: {tail[0]}"
                    )
                self._log.warning(
                    "fpcalc stdout not JSON; filename=%s stdout_head=%r",
                    filename, proc.stdout[:200],
                )
                raise FingerprintError(
                    f"fpcalc stdout was not JSON; output: {proc.stdout[:200]!r}"
                )

            # fpcalc -json fields: duration (float), fingerprint (base64 str)
            result: dict = {
                "duration": float(payload.get("duration", 0.0)),
                "fingerprint": payload.get("fingerprint", ""),
            }
            if return_raw:
                # Use -raw to get the integer array — needs a second call,
                # but only on opt-in because the array can be >10kB.
                raw_cmd = ["fpcalc", "-raw"]
                if analyze_seconds > 0:
                    raw_cmd += ["-length", str(int(analyze_seconds))]
                raw_cmd.append(wav_path)
                raw_proc = subprocess.run(
                    raw_cmd, check=False, capture_output=True, text=True,
                    timeout=300,
                )
                if raw_proc.returncode in (0, 3):
                    for line in (raw_proc.stdout or "").splitlines():
                        if line.startswith("FINGERPRINT="):
                            ints = [
                                int(x) for x in line.split("=", 1)[1].split(",")
                                if x.strip()
                            ]
                            result["fingerprint_raw"] = ints
                            break
            return result
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass
