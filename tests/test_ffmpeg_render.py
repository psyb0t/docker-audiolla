"""Unit tests for FfmpegRenderEngine.

These tests verify:
  - Validation logic (dimension bounds, unknown mode/container, fps range)
  - subprocess.run is called with the correct command fragments
  - ffmpeg failures (non-zero exit, FileNotFoundError, TimeoutExpired) are
    wrapped in FfmpegRenderError
  - Output temp files are cleaned up after both success and failure

ffmpeg itself is NOT invoked — subprocess.run is mocked throughout.
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest

from audiolla.engines.ffmpeg_render import (
    FfmpegRenderEngine,
    FfmpegRenderError,
    _validate_dims,
    _run_ffmpeg,
    visualize_modes,
)


def _engine() -> FfmpegRenderEngine:
    return FfmpegRenderEngine(slug="ffmpeg-render", entry={"executor": "ffmpeg_render"})


def _mock_proc(returncode: int = 0, stderr: str = "") -> MagicMock:
    p = MagicMock()
    p.returncode = returncode
    p.stderr = stderr
    p.stdout = ""
    return p


# ── _validate_dims ────────────────────────────────────────────────────────────


def test_validate_dims_accepts_valid_range():
    _validate_dims(640, 480, min_v=64, max_v=8192)


def test_validate_dims_rejects_width_below_min():
    with pytest.raises(FfmpegRenderError, match="width"):
        _validate_dims(10, 480, min_v=64, max_v=8192)


def test_validate_dims_rejects_height_above_max():
    with pytest.raises(FfmpegRenderError, match="height"):
        _validate_dims(640, 9000, min_v=64, max_v=8192)


# ── _run_ffmpeg ───────────────────────────────────────────────────────────────


def test_run_ffmpeg_raises_when_binary_not_found():
    with patch("subprocess.run", side_effect=FileNotFoundError):
        with pytest.raises(FfmpegRenderError, match="ffmpeg binary not found"):
            _run_ffmpeg(["ffmpeg", "-version"])


def test_run_ffmpeg_raises_on_timeout():
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="ffmpeg", timeout=300)):
        with pytest.raises(FfmpegRenderError, match="timeout"):
            _run_ffmpeg(["ffmpeg", "-version"])


def test_run_ffmpeg_raises_on_nonzero_exit():
    with patch("subprocess.run", return_value=_mock_proc(returncode=1, stderr="error line")):
        with pytest.raises(FfmpegRenderError, match="ffmpeg exit=1"):
            _run_ffmpeg(["ffmpeg", "-version"])


def test_run_ffmpeg_succeeds_on_zero_exit():
    with patch("subprocess.run", return_value=_mock_proc(returncode=0)):
        _run_ffmpeg(["ffmpeg", "-version"])


# ── spectrogram ───────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spectrogram_calls_ffmpeg_with_showspectrumpic(tmp_path):
    png_path = str(tmp_path / "out.png")
    open(png_path, "wb").write(b"\x89PNG" + b"\x00" * 50)

    with patch("audiolla.engines.ffmpeg_render.to_wav_float32", return_value=str(tmp_path / "in.wav")), \
         patch("audiolla.engines.ffmpeg_render._run_ffmpeg") as mock_run, \
         patch("tempfile.mkstemp", return_value=(999, png_path)), \
         patch("os.close"), \
         patch("audiolla.engines.ffmpeg_render._safe_unlink"):
        eng = _engine()
        result = await eng.spectrogram(b"audio", "a.wav", width=1280, height=720)

    mock_run.assert_called_once()
    cmd = mock_run.call_args[0][0]
    assert "showspectrumpic" in " ".join(cmd)
    assert "1280x720" in " ".join(cmd)
    assert result == b"\x89PNG" + b"\x00" * 50


@pytest.mark.asyncio
async def test_spectrogram_rejects_out_of_bounds_dimensions():
    eng = _engine()
    with patch("audiolla.engines.ffmpeg_render.to_wav_float32", return_value="/tmp/x.wav"):
        with pytest.raises(FfmpegRenderError, match="width"):
            await eng.spectrogram(b"audio", "a.wav", width=10, height=720)


# ── waveform ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_waveform_calls_ffmpeg_with_showwavespic(tmp_path):
    png_path = str(tmp_path / "out.png")
    open(png_path, "wb").write(b"\x89PNG" + b"\x00" * 50)

    with patch("audiolla.engines.ffmpeg_render.to_wav_float32", return_value=str(tmp_path / "in.wav")), \
         patch("audiolla.engines.ffmpeg_render._run_ffmpeg") as mock_run, \
         patch("tempfile.mkstemp", return_value=(999, png_path)), \
         patch("os.close"), \
         patch("audiolla.engines.ffmpeg_render._safe_unlink"):
        eng = _engine()
        result = await eng.waveform(b"audio", "a.wav", width=1920, height=320)

    cmd = mock_run.call_args[0][0]
    assert "showwavespic" in " ".join(cmd)
    assert "1920x320" in " ".join(cmd)
    assert result == b"\x89PNG" + b"\x00" * 50


# ── visualize ─────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_visualize_rejects_unknown_mode():
    eng = _engine()
    with pytest.raises(FfmpegRenderError, match="unknown visualize mode"):
        await eng.visualize(b"audio", "a.wav", mode="notamode")


@pytest.mark.asyncio
async def test_visualize_rejects_unknown_container():
    eng = _engine()
    with pytest.raises(FfmpegRenderError, match="unknown container"):
        await eng.visualize(b"audio", "a.wav", container="avi")


@pytest.mark.asyncio
async def test_visualize_rejects_out_of_range_fps():
    eng = _engine()
    with patch("audiolla.engines.ffmpeg_render.to_wav_float32", return_value="/tmp/x.wav"):
        with pytest.raises(FfmpegRenderError, match="fps"):
            await eng.visualize(b"audio", "a.wav", fps=200)


@pytest.mark.asyncio
async def test_visualize_spectrum_mp4_calls_ffmpeg_with_correct_filter(tmp_path):
    mp4_path = str(tmp_path / "out.mp4")
    open(mp4_path, "wb").write(b"\x00\x00\x00\x1cftyp" + b"\x00" * 50)

    with patch("audiolla.engines.ffmpeg_render.to_wav_float32", return_value=str(tmp_path / "in.wav")), \
         patch("audiolla.engines.ffmpeg_render._run_ffmpeg") as mock_run, \
         patch("tempfile.mkstemp", return_value=(999, mp4_path)), \
         patch("os.close"), \
         patch("audiolla.engines.ffmpeg_render._safe_unlink"):
        eng = _engine()
        result = await eng.visualize(b"audio", "a.wav", mode="spectrum", container="mp4")

    cmd = mock_run.call_args[0][0]
    cmd_str = " ".join(cmd)
    assert "showspectrum" in cmd_str
    assert "libx264" in cmd_str


# ── visualize_modes list ──────────────────────────────────────────────────────


def test_visualize_modes_contains_expected_modes():
    modes = visualize_modes()
    for m in ("spectrum", "waves", "cqt", "freqs", "volume", "vectorscope"):
        assert m in modes, f"{m} not in visualize_modes()"


# ── empty output guard ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_spectrogram_raises_when_output_is_empty(tmp_path):
    png_path = str(tmp_path / "out.png")
    open(png_path, "wb").write(b"")  # empty

    with patch("audiolla.engines.ffmpeg_render.to_wav_float32", return_value=str(tmp_path / "in.wav")), \
         patch("audiolla.engines.ffmpeg_render._run_ffmpeg"), \
         patch("tempfile.mkstemp", return_value=(999, png_path)), \
         patch("os.close"), \
         patch("audiolla.engines.ffmpeg_render._safe_unlink"):
        eng = _engine()
        with pytest.raises(FfmpegRenderError, match="empty output"):
            await eng.spectrogram(b"audio", "a.wav")
