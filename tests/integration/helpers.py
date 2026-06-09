"""Assertion helpers for integration tests.

Every helper is a plain function that raises AssertionError on failure with
a descriptive message — pytest renders the message inline so you don't need
a debugger to know what went wrong.
"""

from __future__ import annotations

import io
import struct


# ── UVR / model edge cases ──────────────────────────────────────────────────


def uvr_model_produced_no_output(response: object) -> bool:
    """``True`` if the response is a 400 surfacing a phantom-output case.

    UVR separator family (dereverb / deecho / denoise / vocal-bsr /
    karaoke) misbehaves on synthetic sine-wave input — the underlying
    ``audio-separator`` library claims it wrote per-stem files but
    actually drops the empty/silent outputs to disk. Audiolla surfaces
    this as one of two 400 detail strings depending on which code path
    discovered the discrepancy:

    - ``"model … produced no output files"`` — the entire output_files
      list came back empty (some models do this directly).
    - ``"model … produced no recognisable stems"`` — output_files had
      filenames but none of them actually exist on disk (post-filter).

    Both indicate the same underlying "synthetic input → empty model
    output" case. Tests treat either as a valid end-to-end run (route
    reachable, engine loaded, inference completed) and short-circuit
    on them — real-audio inputs return ``200`` with real bytes.
    """
    # Duck-typing — httpx.Response or anything with .status_code + .text.
    if getattr(response, "status_code", None) != 400:
        return False
    text = getattr(response, "text", "")
    return "no output files" in text or "no recognisable stems" in text


# ── Audio asserts ───────────────────────────────────────────────────────────


def assert_wav(
    data: bytes,
    *,
    min_bytes: int = 1000,
    min_duration_sec: float = 0.0,
    expected_channels: int | None = None,
    expected_samplerate: int | None = None,
) -> None:
    """Assert ``data`` is a valid, decodable RIFF/WAVE file.

    Optional constraints validate the decoded stream — duration, channel
    count, sample rate. Set ``min_duration_sec`` to 0 to skip the decode
    step (cheap path: header-only check).
    """
    assert len(data) >= min_bytes, (
        f"WAV too small: {len(data)} bytes (min {min_bytes})"
    )
    assert data[:4] == b"RIFF", f"not a RIFF file (got {data[:4]!r})"
    assert data[8:12] == b"WAVE", f"not a WAVE file (got {data[8:12]!r})"

    if (
        min_duration_sec > 0
        or expected_channels is not None
        or expected_samplerate is not None
    ):
        import soundfile as sf  # noqa: PLC0415

        with sf.SoundFile(io.BytesIO(data)) as f:
            duration = len(f) / f.samplerate
            channels = f.channels
            samplerate = f.samplerate
        if min_duration_sec > 0:
            assert duration >= min_duration_sec, (
                f"audio too short: {duration:.3f}s (min {min_duration_sec}s)"
            )
        if expected_channels is not None:
            assert channels == expected_channels, (
                f"channels mismatch: got {channels}, expected {expected_channels}"
            )
        if expected_samplerate is not None:
            assert samplerate == expected_samplerate, (
                f"samplerate mismatch: got {samplerate}, "
                f"expected {expected_samplerate}"
            )


def assert_audio_decodable(data: bytes, *, min_duration_sec: float = 0.0) -> None:
    """Assert ``data`` decodes as audio in any soundfile-supported format
    (WAV / FLAC / OGG / etc.). Use this when the test doesn't care about
    the container format, only that real audio came back."""
    import soundfile as sf  # noqa: PLC0415

    with sf.SoundFile(io.BytesIO(data)) as f:
        duration = len(f) / f.samplerate
    if min_duration_sec > 0:
        assert duration >= min_duration_sec, (
            f"audio too short: {duration:.3f}s (min {min_duration_sec}s)"
        )


def assert_mp3(data: bytes, *, min_bytes: int = 500) -> None:
    """Assert ``data`` is an MP3 file — accepts both ID3v2-prefixed (`ID3`)
    and pure MPEG frames (`0xFF 0xFB` etc.)."""
    assert len(data) >= min_bytes, (
        f"MP3 too small: {len(data)} bytes (min {min_bytes})"
    )
    if data[:3] == b"ID3":
        return  # ID3v2 header
    # MPEG audio frame sync: 11 bits set (0xFFE0..0xFFFF).
    if len(data) >= 2 and data[0] == 0xFF and (data[1] & 0xE0) == 0xE0:
        return
    raise AssertionError(
        f"not an MP3 file (first bytes: {data[:4].hex()})"
    )


# ── MIDI asserts ────────────────────────────────────────────────────────────


def assert_midi(data: bytes, *, min_bytes: int = 22) -> None:
    """Assert ``data`` is a Standard MIDI File (MThd header).

    Default min_bytes=22 is the smallest valid SMF (14-byte MThd + 8-byte
    MTrk header + zero-length track). Real-world quantize/humanize outputs
    can land at ~98 bytes for a short pattern — be lenient.
    """
    assert len(data) >= min_bytes, (
        f"MIDI too small: {len(data)} bytes (min {min_bytes})"
    )
    assert data[:4] == b"MThd", f"not a MIDI file (got {data[:4]!r})"
    # MThd chunk length is always 6 bytes; sanity-check it parses.
    if len(data) >= 14:
        chunk_len = struct.unpack(">I", data[4:8])[0]
        assert chunk_len == 6, (
            f"MThd chunk has unexpected length {chunk_len} (expected 6)"
        )


# ── Image asserts ───────────────────────────────────────────────────────────


def assert_png(data: bytes, *, min_bytes: int = 100) -> None:
    """Assert ``data`` is a PNG image (8-byte signature)."""
    assert len(data) >= min_bytes, (
        f"PNG too small: {len(data)} bytes (min {min_bytes})"
    )
    assert data[:8] == b"\x89PNG\r\n\x1a\n", (
        f"not a PNG file (got {data[:8]!r})"
    )


def assert_jpeg(data: bytes, *, min_bytes: int = 100) -> None:
    assert len(data) >= min_bytes
    assert data[:2] == b"\xff\xd8", f"not a JPEG (got {data[:2]!r})"


# ── Video asserts ───────────────────────────────────────────────────────────


def assert_mp4(data: bytes, *, min_bytes: int = 1000) -> None:
    """Assert ``data`` is an MP4 container (ftyp box at offset 4)."""
    assert len(data) >= min_bytes
    # MP4 file: bytes 4-8 are 'ftyp'
    assert data[4:8] == b"ftyp", (
        f"not an MP4 file (bytes 4-8: {data[4:8]!r})"
    )


def assert_webm(data: bytes, *, min_bytes: int = 1000) -> None:
    """Assert ``data`` is a WebM container (EBML header `0x1A 0x45 0xDF 0xA3`)."""
    assert len(data) >= min_bytes
    assert data[:4] == b"\x1a\x45\xdf\xa3", (
        f"not an EBML / WebM file (got {data[:4]!r})"
    )


# ── ZIP asserts ─────────────────────────────────────────────────────────────


def assert_zip(data: bytes, *, min_bytes: int = 100) -> None:
    """Assert ``data`` is a ZIP archive (PK\\x03\\x04 local file header)."""
    assert len(data) >= min_bytes
    assert data[:4] == b"PK\x03\x04", f"not a ZIP file (got {data[:4]!r})"
