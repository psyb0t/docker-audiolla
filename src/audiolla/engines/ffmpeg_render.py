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
import os
import subprocess
import tempfile

from ..audio import AudioConversionError, to_wav_float32
from .base import EngineBase


class FfmpegRenderError(AudioConversionError):
    """ffmpeg failed or the render arguments were rejected."""


# Maps the visualize() ``mode`` argument to the ffmpeg filter spec.
# Each entry is (filter_name, supports_size, supports_rate, default_extra)
# where default_extra is a comma-joined extra arg string applied verbatim.
_VISUALIZE_FILTERS: dict[str, tuple[str, bool, bool, str]] = {
    "spectrum":     ("showspectrum",   True,  True,
                     "mode=combined:slide=scroll:color=intensity:scale=log"),
    "waves":        ("showwaves",      True,  True,  "mode=line:colors=lime"),
    "cqt":          ("showcqt",        True,  True,  ""),
    "freqs":        ("showfreqs",      True,  True,  "mode=bar:fscale=log:cmode=combined"),
    "volume":       ("showvolume",     True,  True,  "f=0.5:b=4"),
    "vectorscope":  ("avectorscope",   True,  True,  "mode=lissajous_xy:zoom=1.5"),
    "phasemeter":   ("aphasemeter",    True,  True,  ""),
    "histogram":    ("ahistogram",     True,  True,  "rheight=1:slide=scroll"),
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
        async with self._lock:
            result = await asyncio.to_thread(
                self._spectrogram_sync, raw, filename, width, height, color, scale,
            )
            self._touch()
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
        async with self._lock:
            result = await asyncio.to_thread(
                self._waveform_sync, raw, filename, width, height, color,
            )
            self._touch()
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
            raise FfmpegRenderError(
                f"unknown visualize mode {mode!r}; "
                f"supported: {sorted(_VISUALIZE_FILTERS)}"
            )
        if container not in _VIDEO_CONTAINERS:
            raise FfmpegRenderError(
                f"unknown container {container!r}; supported: mp4, webm"
            )
        async with self._lock:
            result = await asyncio.to_thread(
                self._visualize_sync,
                raw, filename, mode, width, height, fps, container,
            )
            self._touch()
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

        filt_name, _, _, extra = _VISUALIZE_FILTERS[mode]
        # Build the filter arg string. Size goes as s=WxH; fps is applied
        # as an ffmpeg output -r flag (filter-level rate options vary by filter
        # and are unreliable across ffmpeg versions).
        filt_args = [f"s={width}x{height}"]
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
        raise FfmpegRenderError(
            "ffmpeg binary not found on PATH"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise FfmpegRenderError(
            f"ffmpeg render exceeded {timeout}s timeout"
        ) from exc
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()[-3:] or ["<no stderr>"]
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
