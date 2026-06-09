"""Silence-detection engine — ffmpeg ``silencedetect`` filter.

Locates ranges in an audio file that fall below a given dBFS threshold
for longer than a minimum duration. Returns:
  - silent_ranges        list of {start_sec, end_sec, duration_sec}
  - non_silent_ranges    inverse, useful for "auto-split a DJ mix at quiet
                         spots" workflows
  - duration             total file length

Optionally trims silence — leading + trailing only (``trim_mode=edges``),
or every detected silence (``trim_mode=all``, useful for compressing a
talk recording with long pauses). Trim returns audio bytes.

No model weights — ``get_model()`` is a no-op. CPU-only. Implemented as
a subprocess call to ``ffmpeg`` which is present in every prod image.
"""

from __future__ import annotations

import asyncio
import os
import re
import subprocess
import tempfile
import time

from ..audio import AudioConversionError, encode_audio, write_temp_input
from .base import EngineBase


class SilenceDetectError(AudioConversionError):
    """ffmpeg failed or the threshold/duration args were rejected."""


# Parses lines like:
#   [silencedetect @ 0x...] silence_start: 1.234
#   [silencedetect @ 0x...] silence_end: 5.678 | silence_duration: 4.444
_START_RE = re.compile(r"silence_start:\s*(-?\d+\.?\d*)")
_END_RE = re.compile(r"silence_end:\s*(-?\d+\.?\d*)\s*\|\s*silence_duration:\s*(-?\d+\.?\d*)")
_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.\d+)")


class SilenceDetectEngine(EngineBase):
    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)

    async def detect(
        self,
        raw: bytes,
        filename: str,
        *,
        threshold_db: float = -30.0,
        min_duration_sec: float = 0.5,
        trim_mode: str | None = None,
        output_format: str = "wav",
    ) -> dict:
        if threshold_db > 0:
            self._log.warning("detect: threshold_db > 0: %s", threshold_db)
            raise SilenceDetectError(
                f"threshold_db must be <= 0 dBFS, got {threshold_db}"
            )
        if min_duration_sec <= 0:
            self._log.warning("detect: min_duration_sec <= 0: %s", min_duration_sec)
            raise SilenceDetectError(
                f"min_duration_sec must be > 0, got {min_duration_sec}"
            )
        if trim_mode is not None and trim_mode not in ("edges", "all"):
            self._log.warning("detect: bad trim_mode %r", trim_mode)
            raise SilenceDetectError(
                f"trim_mode must be 'edges' or 'all' (or omit), got {trim_mode!r}"
            )
        self._log.info(
            "detect start: filename=%s input_bytes=%d threshold_db=%.2f "
            "min_duration_sec=%.3f trim_mode=%s output_format=%s",
            filename, len(raw), threshold_db, min_duration_sec, trim_mode,
            output_format,
        )
        t0 = time.perf_counter()
        async with self._lock:
            result = await asyncio.to_thread(
                self._detect_sync,
                raw, filename, threshold_db, min_duration_sec,
                trim_mode, output_format,
            )
            self._touch()
            self._log.info(
                "detect done: filename=%s duration_ms=%.1f silent_ranges=%d",
                filename, (time.perf_counter() - t0) * 1000.0,
                len(result.get("silent_ranges", [])),
            )
            return result

    def _detect_sync(
        self,
        raw: bytes,
        filename: str,
        threshold_db: float,
        min_duration_sec: float,
        trim_mode: str | None,
        output_format: str,
    ) -> dict:
        import base64

        wav_path = write_temp_input(raw, filename)
        try:
            # ffmpeg writes silencedetect events to stderr.
            cmd = [
                "ffmpeg", "-hide_banner", "-nostats",
                "-i", wav_path,
                "-af",
                f"silencedetect=noise={threshold_db}dB:d={min_duration_sec}",
                "-f", "null", "-",
            ]
            try:
                proc = subprocess.run(
                    cmd, check=False, capture_output=True, text=True,
                    timeout=300,
                )
            except FileNotFoundError as exc:
                self._log.exception("ffmpeg binary missing")
                raise SilenceDetectError(
                    "ffmpeg binary not found on PATH"
                ) from exc
            if proc.returncode != 0:
                self._log.warning("ffmpeg detect exit=%d", proc.returncode)
                raise SilenceDetectError(
                    f"ffmpeg exit={proc.returncode}: "
                    f"{(proc.stderr or '').splitlines()[-1:]}"
                )

            duration = _parse_duration(proc.stderr or "")
            ranges = _parse_silence_ranges(proc.stderr or "", duration)
            non_silent = _invert_ranges(ranges, duration)

            result: dict = {
                "silent_ranges": ranges,
                "non_silent_ranges": non_silent,
                "duration": duration,
                "threshold_db": threshold_db,
                "min_duration_sec": min_duration_sec,
            }

            if trim_mode is None:
                return result

            # Build a concat'd WAV from non-silent ranges. For edges-only,
            # take the span [first non-silent start, last non-silent end].
            spans: list[tuple[float, float]]
            if trim_mode == "edges":
                if not non_silent:
                    self._log.warning("detect/edges: entire file silent")
                    raise SilenceDetectError("entire file is silent — nothing to keep")
                spans = [(non_silent[0]["start_sec"], non_silent[-1]["end_sec"])]
            else:  # "all"
                spans = [(s["start_sec"], s["end_sec"]) for s in non_silent]
                if not spans:
                    self._log.warning("detect/all: entire file silent")
                    raise SilenceDetectError("entire file is silent — nothing to keep")

            trimmed = _ffmpeg_concat_spans(wav_path, spans)
            try:
                audio_bytes, _ = encode_audio(trimmed, output_format)
            finally:
                try:
                    os.unlink(trimmed)
                except OSError:
                    pass
            result["trim_mode"] = trim_mode
            result["output_format"] = output_format
            result["trimmed_audio_base64"] = base64.b64encode(audio_bytes).decode("ascii")
            return result
        finally:
            try:
                os.unlink(wav_path)
            except OSError:
                pass


def _parse_duration(stderr: str) -> float:
    m = _DURATION_RE.search(stderr)
    if not m:
        return 0.0
    h, mn, s = m.group(1), m.group(2), m.group(3)
    return int(h) * 3600 + int(mn) * 60 + float(s)


def _parse_silence_ranges(stderr: str, duration: float) -> list[dict]:
    starts = [float(m.group(1)) for m in _START_RE.finditer(stderr)]
    ends_with_dur = [
        (float(m.group(1)), float(m.group(2)))
        for m in _END_RE.finditer(stderr)
    ]
    out: list[dict] = []
    # Pair starts with ends in order. ffmpeg emits them sequentially.
    for i, start in enumerate(starts):
        if i < len(ends_with_dur):
            end, dur = ends_with_dur[i]
        else:
            # Trailing silence — no end marker emitted (file ended in silence).
            end = duration
            dur = duration - start
        out.append({
            "start_sec": float(start),
            "end_sec": float(end),
            "duration_sec": float(dur),
        })
    return out


def _invert_ranges(silent: list[dict], duration: float) -> list[dict]:
    if not silent:
        return [{"start_sec": 0.0, "end_sec": duration}] if duration > 0 else []
    out: list[dict] = []
    cursor = 0.0
    for s in silent:
        if s["start_sec"] > cursor:
            out.append({
                "start_sec": cursor,
                "end_sec": s["start_sec"],
            })
        cursor = s["end_sec"]
    if cursor < duration:
        out.append({
            "start_sec": cursor,
            "end_sec": duration,
        })
    return out


def _ffmpeg_concat_spans(wav_path: str, spans: list[tuple[float, float]]) -> str:
    """Concatenate the given (start, end) seconds spans into a new WAV.
    Returns the new path. Caller is responsible for unlinking it."""
    # Build a single filter_complex that selects + concatenates the spans.
    # For a single span this collapses to a clean -ss / -to trim, but the
    # general path handles N spans uniformly.
    out_fd, out_wav = tempfile.mkstemp(prefix="audiolla-silence-trim-", suffix=".wav")
    os.close(out_fd)

    n = len(spans)
    # asplit the input so each span gets its own stream reference.
    split_outs = "".join(f"[s{i}]" for i in range(n))
    split_part = f"[0:a]asplit={n}{split_outs}"
    trim_parts = [
        f"[s{i}]atrim=start={start}:end={end},asetpts=PTS-STARTPTS[a{i}]"
        for i, (start, end) in enumerate(spans)
    ]
    concat_inputs = "".join(f"[a{i}]" for i in range(n))
    filter_complex = (
        split_part + ";"
        + ";".join(trim_parts)
        + f";{concat_inputs}concat=n={n}:v=0:a=1[outa]"
    )
    cmd = [
        "ffmpeg", "-hide_banner", "-nostats", "-y",
        "-i", wav_path,
        "-filter_complex", filter_complex,
        "-map", "[outa]",
        "-c:a", "pcm_s16le",
        out_wav,
    ]
    proc = subprocess.run(
        cmd, check=False, capture_output=True, text=True, timeout=300,
    )
    if proc.returncode != 0:
        try:
            os.unlink(out_wav)
        except OSError:
            pass
        raise SilenceDetectError(
            f"ffmpeg trim exit={proc.returncode}: "
            f"{(proc.stderr or '').splitlines()[-1:]}"
        )
    return out_wav
