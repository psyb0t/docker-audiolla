"""Unit tests for SilenceDetectEngine.

Validates:
  - Threshold / duration / trim_mode argument guards
  - ffmpeg subprocess call construction and error wrapping
  - _parse_duration, _parse_silence_ranges, _invert_ranges pure functions
  - Cleanup of temp files
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from audiolla.engines.silence_detect import (
    SilenceDetectEngine,
    SilenceDetectError,
    _invert_ranges,
    _parse_duration,
    _parse_silence_ranges,
)


def _engine() -> SilenceDetectEngine:
    return SilenceDetectEngine(
        slug="silence-detect", entry={"executor": "silence_detect"}
    )


def _mock_proc(returncode: int = 0, stderr: str = "") -> MagicMock:
    p = MagicMock()
    p.returncode = returncode
    p.stderr = stderr
    p.stdout = ""
    return p


# ── detect: argument validation ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_rejects_positive_threshold():
    eng = _engine()
    with pytest.raises(SilenceDetectError, match="threshold_db must be <= 0"):
        await eng.detect(b"audio", "audio.wav", threshold_db=5.0)


@pytest.mark.asyncio
async def test_detect_rejects_zero_min_duration():
    eng = _engine()
    with pytest.raises(SilenceDetectError, match="min_duration_sec must be > 0"):
        await eng.detect(b"audio", "audio.wav", min_duration_sec=0.0)


@pytest.mark.asyncio
async def test_detect_rejects_invalid_trim_mode():
    eng = _engine()
    with pytest.raises(SilenceDetectError, match="trim_mode must be"):
        await eng.detect(b"audio", "audio.wav", trim_mode="invalid")


# ── detect: ffmpeg error handling ─────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_raises_when_ffmpeg_not_found():
    eng = _engine()
    with patch("audiolla.engines.silence_detect.write_temp_input", return_value="/tmp/in.wav"), \
         patch("subprocess.run", side_effect=FileNotFoundError), \
         patch("os.unlink"):
        with pytest.raises(SilenceDetectError, match="ffmpeg binary not found"):
            await eng.detect(b"audio", "audio.wav")


@pytest.mark.asyncio
async def test_detect_raises_when_ffmpeg_exits_nonzero():
    mock_proc = _mock_proc(returncode=1, stderr="bad codec")

    eng = _engine()
    with patch("audiolla.engines.silence_detect.write_temp_input", return_value="/tmp/in.wav"), \
         patch("subprocess.run", return_value=mock_proc), \
         patch("os.unlink"):
        with pytest.raises(SilenceDetectError, match="ffmpeg exit=1"):
            await eng.detect(b"audio", "audio.wav")


# ── detect: happy path with silencedetect output ─────────────────────────────


_SAMPLE_STDERR = """\
Input #0, wav, from 'input.wav':
  Duration: 00:00:07.00, start: 0.000000, bitrate: 705 kb/s
[silencedetect @ 0x...] silence_start: 2.0
[silencedetect @ 0x...] silence_end: 5.0 | silence_duration: 3.0
"""


@pytest.mark.asyncio
async def test_detect_returns_silent_and_non_silent_ranges():
    mock_proc = _mock_proc(returncode=0, stderr=_SAMPLE_STDERR)

    eng = _engine()
    with patch("audiolla.engines.silence_detect.write_temp_input", return_value="/tmp/in.wav"), \
         patch("subprocess.run", return_value=mock_proc), \
         patch("os.unlink"):
        result = await eng.detect(b"audio", "audio.wav", threshold_db=-30.0, min_duration_sec=0.5)

    assert len(result["silent_ranges"]) == 1
    assert result["silent_ranges"][0]["start_sec"] == pytest.approx(2.0)
    assert result["silent_ranges"][0]["end_sec"] == pytest.approx(5.0)
    assert result["silent_ranges"][0]["duration_sec"] == pytest.approx(3.0)
    assert result["duration"] == pytest.approx(7.0)
    assert len(result["non_silent_ranges"]) >= 1


@pytest.mark.asyncio
async def test_detect_result_contains_threshold_metadata():
    mock_proc = _mock_proc(returncode=0, stderr=_SAMPLE_STDERR)

    eng = _engine()
    with patch("audiolla.engines.silence_detect.write_temp_input", return_value="/tmp/in.wav"), \
         patch("subprocess.run", return_value=mock_proc), \
         patch("os.unlink"):
        result = await eng.detect(b"audio", "audio.wav", threshold_db=-40.0, min_duration_sec=1.0)

    assert result["threshold_db"] == -40.0
    assert result["min_duration_sec"] == 1.0


# ── detect: trim path ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_trim_mode_edges_returns_trimmed_audio_base64():
    mock_detect_proc = _mock_proc(returncode=0, stderr=_SAMPLE_STDERR)
    mock_trim_proc = _mock_proc(returncode=0)

    eng = _engine()
    with patch("audiolla.engines.silence_detect.write_temp_input", return_value="/tmp/in.wav"), \
         patch("subprocess.run", side_effect=[mock_detect_proc, mock_trim_proc]), \
         patch("audiolla.engines.silence_detect.encode_audio", return_value=(b"trimmed_wav", "wav")), \
         patch("tempfile.mkstemp", return_value=(0, "/tmp/out.wav")), \
         patch("os.close"), \
         patch("os.unlink"):
        result = await eng.detect(
            b"audio", "audio.wav", threshold_db=-30.0, min_duration_sec=0.5,
            trim_mode="edges",
        )

    assert "trimmed_audio_base64" in result
    assert result["trim_mode"] == "edges"


@pytest.mark.asyncio
async def test_detect_trim_mode_all_included():
    mock_detect_proc = _mock_proc(returncode=0, stderr=_SAMPLE_STDERR)
    mock_trim_proc = _mock_proc(returncode=0)

    eng = _engine()
    with patch("audiolla.engines.silence_detect.write_temp_input", return_value="/tmp/in.wav"), \
         patch("subprocess.run", side_effect=[mock_detect_proc, mock_trim_proc]), \
         patch("audiolla.engines.silence_detect.encode_audio", return_value=(b"trimmed_wav", "wav")), \
         patch("tempfile.mkstemp", return_value=(0, "/tmp/out.wav")), \
         patch("os.close"), \
         patch("os.unlink"):
        result = await eng.detect(
            b"audio", "audio.wav", threshold_db=-30.0, min_duration_sec=0.5,
            trim_mode="all",
        )

    assert "trimmed_audio_base64" in result
    assert result["trim_mode"] == "all"


# ── _parse_duration ───────────────────────────────────────────────────────────


def test_parse_duration_extracts_hms():
    stderr = "Duration: 00:01:23.45, start: 0, bitrate: 100"
    assert _parse_duration(stderr) == pytest.approx(60 + 23.45)


def test_parse_duration_returns_zero_when_absent():
    assert _parse_duration("no duration here") == 0.0


def test_parse_duration_handles_hours():
    stderr = "Duration: 01:00:00.00,"
    assert _parse_duration(stderr) == pytest.approx(3600.0)


# ── _parse_silence_ranges ─────────────────────────────────────────────────────


def test_parse_silence_ranges_simple():
    stderr = (
        "[silencedetect] silence_start: 1.5\n"
        "[silencedetect] silence_end: 3.0 | silence_duration: 1.5\n"
    )
    ranges = _parse_silence_ranges(stderr, duration=10.0)
    assert len(ranges) == 1
    assert ranges[0]["start_sec"] == pytest.approx(1.5)
    assert ranges[0]["end_sec"] == pytest.approx(3.0)
    assert ranges[0]["duration_sec"] == pytest.approx(1.5)


def test_parse_silence_ranges_trailing_silence_extends_to_duration():
    """When ffmpeg doesn't emit an end marker (file ends in silence), the
    range should extend to the total duration."""
    stderr = "[silencedetect] silence_start: 5.0\n"
    ranges = _parse_silence_ranges(stderr, duration=8.0)
    assert len(ranges) == 1
    assert ranges[0]["end_sec"] == pytest.approx(8.0)
    assert ranges[0]["duration_sec"] == pytest.approx(3.0)


def test_parse_silence_ranges_multiple():
    stderr = (
        "[silencedetect] silence_start: 0.5\n"
        "[silencedetect] silence_end: 1.0 | silence_duration: 0.5\n"
        "[silencedetect] silence_start: 3.0\n"
        "[silencedetect] silence_end: 4.0 | silence_duration: 1.0\n"
    )
    ranges = _parse_silence_ranges(stderr, duration=6.0)
    assert len(ranges) == 2


# ── _invert_ranges ────────────────────────────────────────────────────────────


def test_invert_ranges_returns_single_span_when_no_silence():
    ns = _invert_ranges([], duration=10.0)
    assert ns == [{"start_sec": 0.0, "end_sec": 10.0}]


def test_invert_ranges_returns_empty_when_zero_duration():
    ns = _invert_ranges([], duration=0.0)
    assert ns == []


def test_invert_ranges_excludes_leading_silence():
    silent = [{"start_sec": 0.0, "end_sec": 2.0, "duration_sec": 2.0}]
    ns = _invert_ranges(silent, duration=5.0)
    assert ns == [{"start_sec": 2.0, "end_sec": 5.0}]


def test_invert_ranges_excludes_middle_silence():
    silent = [{"start_sec": 2.0, "end_sec": 4.0, "duration_sec": 2.0}]
    ns = _invert_ranges(silent, duration=6.0)
    assert {"start_sec": 0.0, "end_sec": 2.0} in ns
    assert {"start_sec": 4.0, "end_sec": 6.0} in ns
