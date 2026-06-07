"""Unit tests for audiolla.audio — content-type table + zip helper +
AudioConversionError boundary. ffmpeg invocations are not covered here
(they need the ffmpeg binary and a real audio file; covered by the
integration suite)."""

from __future__ import annotations

import io
import zipfile

import pytest

from audiolla.audio import (
    AudioConversionError,
    SUPPORTED_OUTPUT_FORMATS,
    content_type_for,
    multi_stream_zip,
)


# ── content_type_for ─────────────────────────────────────────────────────────

def test_content_type_known_formats():
    assert content_type_for("wav") == "audio/wav"
    assert content_type_for("mp3") == "audio/mpeg"
    assert content_type_for("flac") == "audio/flac"
    assert content_type_for("opus").startswith("audio/ogg")
    assert content_type_for("aac") == "audio/aac"
    assert content_type_for("pcm") == "audio/pcm"


def test_content_type_unknown_format_falls_back():
    assert content_type_for("ufoXYZ") == "application/octet-stream"


def test_supported_output_formats_complete():
    # Every supported format must have a content-type mapping.
    for fmt in SUPPORTED_OUTPUT_FORMATS:
        assert content_type_for(fmt) != "application/octet-stream"


# ── multi_stream_zip ─────────────────────────────────────────────────────────

def test_multi_stream_zip_packs_streams():
    streams = {
        "vocals": b"V" * 100,
        "drums": b"D" * 200,
    }
    blob = multi_stream_zip(streams, "wav")
    # Returned blob is a valid ZIP with two members named <stem>.<fmt>.
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        names = sorted(zf.namelist())
        assert names == ["drums.wav", "vocals.wav"]
        assert zf.read("vocals.wav") == streams["vocals"]
        assert zf.read("drums.wav") == streams["drums"]


def test_multi_stream_zip_honours_output_format():
    streams = {"x": b"xxx"}
    blob = multi_stream_zip(streams, "flac")
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert zf.namelist() == ["x.flac"]


def test_multi_stream_zip_empty_dict():
    blob = multi_stream_zip({}, "wav")
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        assert zf.namelist() == []


# ── AudioConversionError ─────────────────────────────────────────────────────

def test_audio_conversion_error_is_exception():
    # The server route handlers map this to HTTP 400. Confirm it's a real
    # Exception subclass (not a misnamed dataclass).
    with pytest.raises(AudioConversionError, match="oops"):
        raise AudioConversionError("oops")


# ── write_temp_input (no ffmpeg needed) ──────────────────────────────────────

def test_write_temp_input_basic(tmp_path, monkeypatch):
    from audiolla.audio import write_temp_input

    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    path = write_temp_input(b"some bytes", "song.mp3")
    try:
        assert path.endswith(".mp3")
        with open(path, "rb") as fh:
            assert fh.read() == b"some bytes"
    finally:
        import os
        os.unlink(path)


def test_write_temp_input_rejects_empty():
    from audiolla.audio import write_temp_input

    with pytest.raises(AudioConversionError, match="empty"):
        write_temp_input(b"", "x.mp3")


def test_write_temp_input_strips_suspicious_extensions(tmp_path, monkeypatch):
    from audiolla.audio import write_temp_input

    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    # extension > 8 chars is rejected → falls back to no suffix
    path = write_temp_input(b"x", "song.exemely_long_extension")
    try:
        assert not path.endswith("exemely_long_extension")
    finally:
        import os
        os.unlink(path)


def test_write_temp_input_no_extension(tmp_path, monkeypatch):
    from audiolla.audio import write_temp_input

    monkeypatch.setattr("tempfile.tempdir", str(tmp_path))
    path = write_temp_input(b"x", "no_extension_here")
    try:
        # No "." in filename → no suffix on temp file
        assert "." not in path.rsplit("/", 1)[-1] or path.endswith(".tmp")
    finally:
        import os
        os.unlink(path)


# ── _run_ffmpeg error paths (mocked subprocess) ──────────────────────────────

def test_run_ffmpeg_raises_on_nonzero(monkeypatch):
    from audiolla.audio import _run_ffmpeg
    import subprocess

    class _FakeProc:
        returncode = 1
        stderr = b"ffmpeg: bad input file"

    def fake_run(*_a, **_kw):
        return _FakeProc()

    monkeypatch.setattr(subprocess, "run", fake_run)
    with pytest.raises(AudioConversionError, match="bad input file"):
        _run_ffmpeg(["ffmpeg", "-i", "fake"])


def test_run_ffmpeg_passes_on_zero(monkeypatch):
    from audiolla.audio import _run_ffmpeg
    import subprocess

    class _FakeProc:
        returncode = 0
        stderr = b""

    monkeypatch.setattr(subprocess, "run", lambda *a, **kw: _FakeProc())
    _run_ffmpeg(["ffmpeg", "-i", "ok"])  # no exception


# ── multiband_compress validation ───────────────────────────────────────────
#
# The processing path needs numpy + scipy + pedalboard + soundfile + ffmpeg
# (covered by the integration suite). These tests exercise just the cheap
# validation paths that reject malformed inputs before any heavy import.

def test_multiband_compress_rejects_empty_crossovers():
    from audiolla.audio import multiband_compress

    with pytest.raises(AudioConversionError, match="non-empty list"):
        multiband_compress(b"x", "a.wav", crossovers_hz=[], bands=[])


def test_multiband_compress_rejects_bands_length_mismatch():
    from audiolla.audio import multiband_compress

    # 1 crossover requires 2 bands, only 1 supplied
    with pytest.raises(AudioConversionError, match="length len\\(crossovers_hz\\)\\+1"):
        multiband_compress(
            b"x", "a.wav", crossovers_hz=[1000], bands=[{"threshold_db": -10, "ratio": 2}]
        )


def test_multiband_compress_rejects_non_positive_crossover():
    from audiolla.audio import multiband_compress

    with pytest.raises(AudioConversionError, match="must be > 0 Hz"):
        multiband_compress(
            b"x", "a.wav", crossovers_hz=[-100], bands=[{}, {}]
        )


def test_multiband_compress_rejects_bad_output_format():
    from audiolla.audio import multiband_compress

    with pytest.raises(AudioConversionError, match="unsupported output format"):
        multiband_compress(
            b"x", "a.wav", crossovers_hz=[1000], bands=[{}, {}],
            output_format="bogus",
        )
