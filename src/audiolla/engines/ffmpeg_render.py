"""ffmpeg-based audio visualisation engine.

Three methods:

  spectrogram(...)  →  PNG (static, via ``showspectrumpic``)
  waveform(...)     →  PNG (static, via ``showwavespic``)
  visualize(...)    →  MP4 / WebM video (animated, via the selectable
                       ``mode`` mapped to one of ffmpeg's ``show*`` filters)

Visualisation modes for ``visualize()``:

  spectrum      ``showspectrum``       scrolling FFT, classic spectrum analyzer
  waves         ``showwaves``          oscilloscope-style waveform
  cqt           ``showcqt``            constant-Q transform, musical pitch bars
  freqs         ``showfreqs``          live bar-graph frequency analyzer
  volume        ``showvolume``         per-channel VU meter
  vectorscope   ``avectorscope``       stereo correlation X/Y scope
  phasemeter    ``aphasemeter``        L/R phase indicator
  histogram     ``ahistogram``         sample-value histogram over time

All outputs go through the same ``encode_audio``-style temp-file pattern
so the caller never sees ffmpeg's invocation. CPU-only. No model weights.

Note on dimensions: ffmpeg filters generally accept ``s=WxH`` for the
output size. We default to 1280×720 for video, 1920×1080 for static
images. fps defaults to 30 for video.
"""

from __future__ import annotations

import asyncio
import logging
import os
import subprocess
import tempfile
import time

from ..audio import AudioConversionError, to_wav_float32
from .base import EngineBase

_log = logging.getLogger("audiolla.engine.ffmpeg_render")


class FfmpegRenderError(AudioConversionError):
    """ffmpeg failed or the render arguments were rejected."""


# Maps the visualize() ``mode`` argument to the ffmpeg filter spec.
# Each entry is (filter_name, size_arg_style, supports_rate, default_extra)
# where size_arg_style is one of:
#   "wh"  → "w=W:h=H" (showvolume + a few others — `s=WxH` is rejected)
#   "s"   → "s=WxH"   (most show* / a* filters)
#   None  → don't pass size at all
_VISUALIZE_FILTERS: dict[str, tuple[str, str | None, bool, str]] = {
    "spectrum":     ("showspectrum",   "s",  True,
                     "mode=combined:slide=scroll:color=intensity:scale=log"),
    "waves":        ("showwaves",      "s",  True,  "mode=line:colors=lime"),
    "cqt":          ("showcqt",        "s",  True,  ""),
    "freqs":        ("showfreqs",      "s",  True,  "mode=bar:fscale=log:cmode=combined"),
    # showvolume rejects `s=WxH` ("Invalid argument" on the `s` option);
    # it takes `w=` + `h=` separately.
    "volume":       ("showvolume",     "wh", True,  "f=0.5:b=4"),
    "vectorscope":  ("avectorscope",   "s",  True,  "mode=lissajous_xy:zoom=1.5"),
    "phasemeter":   ("aphasemeter",    "s",  True,  ""),
    "histogram":    ("ahistogram",     "s",  True,  "rheight=1:slide=scroll"),
}

_VIDEO_CONTAINERS = {
    "mp4":  ("libx264", "aac"),
    "webm": ("libvpx-vp9", "libopus"),
}


class FfmpegRenderEngine(EngineBase):
    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)

    # ── static spectrogram PNG ─────────────────────────────────────────────

    async def spectrogram(
        self,
        raw: bytes,
        filename: str,
        *,
        width: int = 1920,
        height: int = 1080,
        color: str = "intensity",
        scale: str = "log",
    ) -> bytes:
        self._log.info(
            "spectrogram start: filename=%s input_bytes=%d dims=%dx%d color=%s scale=%s",
            filename, len(raw), width, height, color, scale,
        )
        t0 = time.perf_counter()
        async with self._lock:
            result = await asyncio.to_thread(
                self._spectrogram_sync, raw, filename, width, height, color, scale,
            )
            self._touch()
            self._log.info(
                "spectrogram done: filename=%s duration_ms=%.1f png_bytes=%d",
                filename, (time.perf_counter() - t0) * 1000.0, len(result),
            )
            return result

    def _spectrogram_sync(
        self,
        raw: bytes,
        filename: str,
        width: int,
        height: int,
        color: str,
        scale: str,
    ) -> bytes:
        _validate_dims(width, height, min_v=64, max_v=8192)
        wav_path = to_wav_float32(raw, filename)
        out_fd, out_png = tempfile.mkstemp(prefix="audiolla-spec-", suffix=".png")
        os.close(out_fd)
        try:
            cmd = [
                "ffmpeg", "-hide_banner", "-nostats", "-y",
                "-i", wav_path,
                "-lavfi",
                f"showspectrumpic=s={width}x{height}"
                f":color={color}:scale={scale}:legend=1",
                "-frames:v", "1",
                out_png,
            ]
            _run_ffmpeg(cmd)
            return _read_bytes(out_png)
        finally:
            _safe_unlink(wav_path, out_png)

    # ── static waveform PNG ────────────────────────────────────────────────

    async def waveform(
        self,
        raw: bytes,
        filename: str,
        *,
        width: int = 1920,
        height: int = 320,
        color: str = "lime",
    ) -> bytes:
        self._log.info(
            "waveform start: filename=%s input_bytes=%d dims=%dx%d color=%s",
            filename, len(raw), width, height, color,
        )
        t0 = time.perf_counter()
        async with self._lock:
            result = await asyncio.to_thread(
                self._waveform_sync, raw, filename, width, height, color,
            )
            self._touch()
            self._log.info(
                "waveform done: filename=%s duration_ms=%.1f png_bytes=%d",
                filename, (time.perf_counter() - t0) * 1000.0, len(result),
            )
            return result

    def _waveform_sync(
        self,
        raw: bytes,
        filename: str,
        width: int,
        height: int,
        color: str,
    ) -> bytes:
        _validate_dims(width, height, min_v=64, max_v=8192)
        wav_path = to_wav_float32(raw, filename)
        out_fd, out_png = tempfile.mkstemp(prefix="audiolla-wave-", suffix=".png")
        os.close(out_fd)
        try:
            cmd = [
                "ffmpeg", "-hide_banner", "-nostats", "-y",
                "-i", wav_path,
                "-filter_complex",
                f"showwavespic=s={width}x{height}:colors={color}",
                "-frames:v", "1",
                out_png,
            ]
            _run_ffmpeg(cmd)
            return _read_bytes(out_png)
        finally:
            _safe_unlink(wav_path, out_png)

    # ── animated visualisation video ───────────────────────────────────────

    async def visualize(
        self,
        raw: bytes,
        filename: str,
        *,
        mode: str = "spectrum",
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        container: str = "mp4",
    ) -> bytes:
        if mode not in _VISUALIZE_FILTERS:
            self._log.warning(
                "visualize rejected: unknown mode=%s filename=%s", mode, filename,
            )
            raise FfmpegRenderError(
                f"unknown visualize mode {mode!r}; "
                f"supported: {sorted(_VISUALIZE_FILTERS)}"
            )
        if container not in _VIDEO_CONTAINERS:
            self._log.warning(
                "visualize rejected: unknown container=%s filename=%s",
                container, filename,
            )
            raise FfmpegRenderError(
                f"unknown container {container!r}; supported: mp4, webm"
            )
        self._log.info(
            "visualize start: filename=%s input_bytes=%d mode=%s dims=%dx%d fps=%d container=%s",
            filename, len(raw), mode, width, height, fps, container,
        )
        t0 = time.perf_counter()
        async with self._lock:
            result = await asyncio.to_thread(
                self._visualize_sync,
                raw, filename, mode, width, height, fps, container,
            )
            self._touch()
            self._log.info(
                "visualize done: filename=%s mode=%s duration_ms=%.1f output_bytes=%d",
                filename, mode, (time.perf_counter() - t0) * 1000.0, len(result),
            )
            return result

    def _visualize_sync(
        self,
        raw: bytes,
        filename: str,
        mode: str,
        width: int,
        height: int,
        fps: int,
        container: str,
    ) -> bytes:
        _validate_dims(width, height, min_v=64, max_v=3840)
        if fps < 1 or fps > 120:
            raise FfmpegRenderError(f"fps must be in [1, 120], got {fps}")

        filt_name, size_style, _, extra = _VISUALIZE_FILTERS[mode]
        # Build the filter arg string. Most filters take `s=WxH`;
        # showvolume rejects that and wants `w=W:h=H`. fps is applied
        # as an ffmpeg output -r flag (filter-level rate options vary
        # by filter and are unreliable across ffmpeg versions).
        filt_args: list[str] = []
        if size_style == "s":
            filt_args.append(f"s={width}x{height}")
        elif size_style == "wh":
            filt_args.append(f"w={width}:h={height}")
        # else: no size passed (filter doesn't accept dimensions)
        if extra:
            filt_args.append(extra)
        filter_spec = f"[0:a]{filt_name}=" + ":".join(filt_args) + "[v]"

        video_codec, audio_codec = _VIDEO_CONTAINERS[container]
        wav_path = to_wav_float32(raw, filename)
        out_fd, out_path = tempfile.mkstemp(
            prefix="audiolla-viz-", suffix=f".{container}"
        )
        os.close(out_fd)
        try:
            cmd = [
                "ffmpeg", "-hide_banner", "-nostats", "-y",
                "-i", wav_path,
                "-filter_complex", filter_spec,
                "-map", "[v]",
                "-map", "0:a",
                "-r", str(fps),
                "-c:v", video_codec,
                "-pix_fmt", "yuv420p",
                "-c:a", audio_codec,
                "-shortest",
                out_path,
            ]
            _run_ffmpeg(cmd, timeout=600)
            return _read_bytes(out_path)
        finally:
            _safe_unlink(wav_path, out_path)


# ── helpers ──────────────────────────────────────────────────────────────────


def _validate_dims(width: int, height: int, *, min_v: int, max_v: int) -> None:
    if width < min_v or width > max_v:
        raise FfmpegRenderError(f"width must be in [{min_v}, {max_v}], got {width}")
    if height < min_v or height > max_v:
        raise FfmpegRenderError(f"height must be in [{min_v}, {max_v}], got {height}")


def _run_ffmpeg(cmd: list[str], *, timeout: int = 300) -> None:
    try:
        proc = subprocess.run(
            cmd, check=False, capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError as exc:
        _log.exception("ffmpeg binary not found on PATH")
        raise FfmpegRenderError(
            "ffmpeg binary not found on PATH"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        _log.warning("ffmpeg render exceeded %ds timeout", timeout)
        raise FfmpegRenderError(
            f"ffmpeg render exceeded {timeout}s timeout"
        ) from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-3:] or ["<no stderr>"]
        _log.warning(
            "ffmpeg exit=%d stderr_tail=%s", proc.returncode, " | ".join(tail),
        )
        raise FfmpegRenderError(
            f"ffmpeg exit={proc.returncode}: {' | '.join(tail)}"
        )


def _read_bytes(path: str) -> bytes:
    with open(path, "rb") as fh:
        data = fh.read()
    if not data:
        raise FfmpegRenderError(f"ffmpeg produced empty output at {path}")
    return data


def _safe_unlink(*paths: str) -> None:
    for p in paths:
        try:
            os.unlink(p)
        except OSError:
            pass


def visualize_modes() -> list[str]:
    """Exposed for the OpenAPI spec + docs."""
    return sorted(_VISUALIZE_FILTERS)
