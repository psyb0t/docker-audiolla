"""Audio DSP toolkit — ffmpeg / scipy / pedalboard wrappers.

Stateless functions only. Anything that needs lazy model load, lock, or
lifecycle management belongs in `engines/` instead (see CLAUDE.md).

Sections (search for the banner to navigate):

  CORE         AudioConversionError, format tables, encode/decode helpers,
               audio_info, multi_stream_zip, _run_ffmpeg
  TRANSFORM    trim, mix, concat, speed, convert, fade, reverse, loop,
               stereo_width, split_audio_equal, pan, eq
  STEREO       mid_side_encode/decode, stereo_field
  DYNAMICS     sidechain_duck, transient_shape, multiband_compress, deess
  RESTORE      clip_detect, repair_audio
  EFFECTS      beat_slice, conv_reverb
  ANALYZE      loudness_curve
  MIDI         chords_to_midi_bytes
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import logging

_log = logging.getLogger("audiolla.audio")


# ═══════════════════════════════════════════════════════════════════════════
# CORE — error class, format tables, ffmpeg encode/decode, audio_info
# ═══════════════════════════════════════════════════════════════════════════


class AudioConversionError(Exception):
    pass


SUPPORTED_OUTPUT_FORMATS = frozenset({"wav", "mp3", "flac", "opus", "aac", "pcm"})

_FORMAT_CONTENT_TYPE = {
    "wav": "audio/wav",
    "mp3": "audio/mpeg",
    "flac": "audio/flac",
    "opus": "audio/ogg; codecs=opus",
    "aac": "audio/aac",
    "pcm": "audio/pcm",
}

_FORMAT_FFMPEG_CODEC = {
    "wav": ["-f", "wav", "-c:a", "pcm_s16le"],
    "mp3": ["-f", "mp3", "-b:a", "192k"],
    "flac": ["-f", "flac"],
    "opus": ["-f", "ogg", "-c:a", "libopus", "-b:a", "128k"],
    "aac": ["-f", "adts", "-c:a", "aac", "-b:a", "192k"],
    "pcm": ["-f", "s16le"],
}


def content_type_for(fmt: str) -> str:
    return _FORMAT_CONTENT_TYPE.get(fmt, "application/octet-stream")


def write_temp_input(raw_bytes: bytes, original_filename: str) -> str:
    if not raw_bytes:
        raise AudioConversionError("upload is empty")
    suffix = ""
    if "." in original_filename:
        ext = original_filename.rsplit(".", 1)[-1].lower()
        if ext and len(ext) <= 8:
            suffix = "." + ext
    in_fd, in_path = tempfile.mkstemp(prefix="audiolla-in-", suffix=suffix)
    try:
        with os.fdopen(in_fd, "wb") as fh:
            fh.write(raw_bytes)
    except Exception:
        os.unlink(in_path)
        raise
    return in_path


def to_wav_float32(raw_bytes: bytes, original_filename: str) -> str:
    """Decode any audio format to 32-bit float stereo WAV. Returns temp file path.

    ``-c:a pcm_f32le`` is required — without an explicit codec ffmpeg
    defaults to pcm_s16le, which doesn't support ``-sample_fmt flt``.
    """
    in_path = write_temp_input(raw_bytes, original_filename)
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-dec-", suffix=".wav")
    os.close(out_fd)
    try:
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", in_path,
            "-ar", "44100",
            "-ac", "2",
            "-c:a", "pcm_f32le",
            out_path,
        ])
    except Exception:
        os.unlink(out_path)
        raise
    finally:
        os.unlink(in_path)
    return out_path


def encode_audio(wav_path: str, output_format: str) -> tuple[bytes, str]:
    """Encode a WAV file to the requested output format. Returns (bytes, content_type)."""
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-enc-")
    os.close(out_fd)
    try:
        _run_ffmpeg(["ffmpeg", "-y", "-i", wav_path] + codec_args + [out_path])
        with open(out_path, "rb") as fh:
            data = fh.read()
    finally:
        os.unlink(out_path)
    return data, content_type_for(output_format)


_SAMPLE_FMT_BIT_DEPTH: dict[str, int] = {
    "u8": 8, "u8p": 8,
    "s16": 16, "s16p": 16,
    "s32": 32, "s32p": 32, "flt": 32, "fltp": 32,
    "dbl": 64, "dblp": 64, "s64": 64, "s64p": 64,
}


def audio_info(raw_bytes: bytes, original_filename: str) -> dict:
    """Probe audio metadata via ffprobe. Returns duration, codec, channels, etc."""
    import json as _json

    in_path = write_temp_input(raw_bytes, original_filename)
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-print_format", "json",
                "-show_streams", "-show_format",
                in_path,
            ],
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            raise AudioConversionError(f"ffprobe failed: {stderr or 'unknown error'}")
        data = _json.loads(proc.stdout.decode("utf-8", errors="replace"))
    finally:
        os.unlink(in_path)

    streams = data.get("streams", [])
    audio_stream = next((s for s in streams if s.get("codec_type") == "audio"), None)
    fmt = data.get("format", {})

    if audio_stream is None:
        raise AudioConversionError("no audio stream found in file")

    sample_fmt = audio_stream.get("sample_fmt", "")
    bit_depth = _SAMPLE_FMT_BIT_DEPTH.get(sample_fmt)

    raw_bit_rate = audio_stream.get("bit_rate") or fmt.get("bit_rate")
    bit_rate: int | None = None
    if raw_bit_rate is not None:
        try:
            bit_rate = int(raw_bit_rate)
        except (ValueError, TypeError):
            pass

    frames: int | None = None
    raw_frames = audio_stream.get("nb_frames")
    if raw_frames is not None:
        try:
            frames = int(raw_frames)
        except (ValueError, TypeError):
            pass

    raw_duration = audio_stream.get("duration") or fmt.get("duration")
    try:
        duration_sec = round(float(raw_duration), 6) if raw_duration is not None else 0.0
    except (ValueError, TypeError):
        duration_sec = 0.0

    result: dict = {
        "size_bytes": len(raw_bytes),
        "duration_sec": duration_sec,
        "sample_rate": int(audio_stream.get("sample_rate", 0)),
        "channels": int(audio_stream.get("channels", 0)),
        "codec": audio_stream.get("codec_name", ""),
        "sample_fmt": sample_fmt,
        "format": fmt.get("format_name", ""),
    }
    if bit_depth is not None:
        result["bit_depth"] = bit_depth
    if bit_rate is not None:
        result["bit_rate"] = bit_rate
    if frames is not None:
        result["frames"] = frames
    return result


# ═══════════════════════════════════════════════════════════════════════════
# TRANSFORM — basic ops: trim, mix, concat, speed, convert, fade, reverse,
#             loop, stereo_width, split_audio_equal, pan, eq
# ═══════════════════════════════════════════════════════════════════════════


def trim_audio(
    raw_bytes: bytes,
    original_filename: str,
    start_sec: float,
    end_sec: float,
    output_format: str,
) -> bytes:
    """Cut audio to [start_sec, end_sec) and re-encode to output_format."""
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    in_path = write_temp_input(raw_bytes, original_filename)
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-trim-")
    os.close(out_fd)
    try:
        _run_ffmpeg(
            ["ffmpeg", "-y", "-ss", str(start_sec), "-to", str(end_sec), "-i", in_path]
            + codec_args
            + [out_path]
        )
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def mix_audio(inputs: list[tuple[bytes, str, float]], output_format: str) -> bytes:
    """Mix N audio tracks with per-track gain_db. Requires at least 2 inputs."""
    if len(inputs) < 2:
        raise AudioConversionError("mix_audio requires at least 2 inputs")
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    in_paths: list[str] = []
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-mix-")
    os.close(out_fd)
    try:
        for raw_bytes, filename, _ in inputs:
            in_paths.append(write_temp_input(raw_bytes, filename))

        filter_parts: list[str] = []
        for i, (_, _, gain_db) in enumerate(inputs):
            linear = 10 ** (gain_db / 20.0)
            filter_parts.append(f"[{i}:a]volume={linear}[a{i}]")
        mixed_inputs = "".join(f"[a{i}]" for i in range(len(inputs)))
        filter_parts.append(
            f"{mixed_inputs}amix=inputs={len(inputs)}:duration=longest:normalize=0[out]"
        )
        filter_complex = ";".join(filter_parts)

        cmd = ["ffmpeg", "-y"]
        for p in in_paths:
            cmd += ["-i", p]
        cmd += ["-filter_complex", filter_complex, "-map", "[out]"]
        cmd += codec_args
        cmd.append(out_path)

        _run_ffmpeg(cmd)
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        for p in in_paths:
            if os.path.exists(p):
                os.unlink(p)
        if os.path.exists(out_path):
            os.unlink(out_path)


def concat_audio(inputs: list[tuple[bytes, str]], output_format: str) -> bytes:
    """Concatenate N audio files in order. Requires at least 2 inputs."""
    if len(inputs) < 2:
        raise AudioConversionError("concat_audio requires at least 2 inputs")
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    in_paths: list[str] = []
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-concat-")
    os.close(out_fd)
    try:
        for raw_bytes, filename in inputs:
            in_paths.append(write_temp_input(raw_bytes, filename))

        n = len(inputs)
        input_labels = "".join(f"[{i}:a]" for i in range(n))
        filter_complex = f"{input_labels}concat=n={n}:v=0:a=1[out]"

        cmd = ["ffmpeg", "-y"]
        for p in in_paths:
            cmd += ["-i", p]
        cmd += ["-filter_complex", filter_complex, "-map", "[out]"]
        cmd += codec_args
        cmd.append(out_path)

        _run_ffmpeg(cmd)
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        for p in in_paths:
            if os.path.exists(p):
                os.unlink(p)
        if os.path.exists(out_path):
            os.unlink(out_path)


def speed_audio(
    raw_bytes: bytes,
    original_filename: str,
    speed: float,
    output_format: str,
) -> bytes:
    """Change playback speed without pitch shift via ffmpeg atempo.
    speed=0.5 → half speed; speed=2.0 → double speed.
    atempo only supports [0.5, 2.0] per filter; chain multiple for extreme values."""
    if not (0.1 <= speed <= 10.0):
        raise AudioConversionError(
            f"speed must be in [0.1, 10.0], got {speed}"
        )
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    in_path = write_temp_input(raw_bytes, original_filename)
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-speed-")
    os.close(out_fd)
    try:
        remaining = speed
        atempo_parts: list[str] = []
        while remaining > 2.0:
            atempo_parts.append("atempo=2.0")
            remaining /= 2.0
        while remaining < 0.5:
            atempo_parts.append("atempo=0.5")
            remaining /= 0.5
        atempo_parts.append(f"atempo={remaining}")
        atempo_filter = ",".join(atempo_parts)

        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", in_path, "-af", atempo_filter]
            + codec_args
            + [out_path]
        )
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def convert_audio(
    raw_bytes: bytes,
    original_filename: str,
    output_format: str,
    sample_rate: int | None = None,
    channels: int | None = None,
) -> bytes:
    """Re-encode audio: format, sample_rate, and/or channel count conversion."""
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    if sample_rate is not None and sample_rate <= 0:
        raise AudioConversionError(f"sample_rate must be > 0, got {sample_rate}")
    if channels is not None and channels not in (1, 2):
        raise AudioConversionError(f"channels must be 1 or 2, got {channels}")
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    in_path = write_temp_input(raw_bytes, original_filename)
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-conv-")
    os.close(out_fd)
    try:
        cmd = ["ffmpeg", "-y", "-i", in_path]
        if sample_rate is not None:
            cmd += ["-ar", str(sample_rate)]
        if channels is not None:
            cmd += ["-ac", str(channels)]
        cmd += codec_args
        cmd.append(out_path)
        _run_ffmpeg(cmd)
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


_FADE_CURVES = frozenset({
    "tri", "qsin", "esin", "hsin", "log", "ipar", "qua",
    "cub", "squ", "cbr", "par", "exp", "lin",
})


def fade_audio(
    raw_bytes: bytes,
    original_filename: str,
    output_format: str,
    fade_in: float = 0.0,
    fade_out: float = 0.0,
    curve: str = "tri",
) -> bytes:
    if fade_in < 0 or fade_out < 0:
        raise AudioConversionError("fade_in and fade_out must be >= 0")
    if fade_in == 0.0 and fade_out == 0.0:
        raise AudioConversionError("at least one of fade_in or fade_out must be > 0")
    if curve not in _FADE_CURVES:
        raise AudioConversionError(
            f"unsupported curve {curve!r}; supported: {sorted(_FADE_CURVES)}"
        )
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    in_path = write_temp_input(raw_bytes, original_filename)
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-fade-")
    os.close(out_fd)
    try:
        filter_parts: list[str] = []
        if fade_in > 0:
            filter_parts.append(f"afade=t=in:d={fade_in}:curve={curve}")
        if fade_out > 0:
            proc = subprocess.run(
                [
                    "ffprobe", "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "default=noprint_wrappers=1:nokey=1",
                    in_path,
                ],
                capture_output=True,
                timeout=60,
            )
            duration = float(proc.stdout.decode().strip())
            st = max(0.0, duration - fade_out)
            filter_parts.append(f"afade=t=out:st={st}:d={fade_out}:curve={curve}")
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", in_path, "-af", ",".join(filter_parts)]
            + codec_args
            + [out_path]
        )
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def reverse_audio(
    raw_bytes: bytes,
    original_filename: str,
    output_format: str,
) -> bytes:
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    in_path = write_temp_input(raw_bytes, original_filename)
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-reverse-")
    os.close(out_fd)
    try:
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", in_path, "-af", "areverse"]
            + codec_args
            + [out_path]
        )
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def loop_audio(
    raw_bytes: bytes,
    original_filename: str,
    output_format: str,
    count: int = 2,
) -> bytes:
    if count < 2:
        raise AudioConversionError("count must be >= 2")
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    in_path = write_temp_input(raw_bytes, original_filename)
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-loop-")
    os.close(out_fd)
    try:
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", in_path,
             "-af", f"aloop=loop={count - 1}:size=2147483647"]
            + codec_args
            + [out_path]
        )
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def stereo_width_audio(
    raw_bytes: bytes,
    original_filename: str,
    output_format: str,
    width: float = 1.0,
) -> bytes:
    if not (0.0 <= width <= 3.0):
        raise AudioConversionError(
            f"width must be in [0.0, 3.0], got {width}"
        )
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    a = (1.0 + width) / 2.0
    b = (1.0 - width) / 2.0
    pan_filter = (
        f"aformat=channel_layouts=stereo,"
        f"pan=stereo|c0={a}*c0+{b}*c1|c1={b}*c0+{a}*c1"
    )
    in_path = write_temp_input(raw_bytes, original_filename)
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-stereowidth-")
    os.close(out_fd)
    try:
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", in_path, "-af", pan_filter]
            + codec_args
            + [out_path]
        )
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def split_audio_equal(
    raw_bytes: bytes,
    original_filename: str,
    output_format: str,
    count: int,
) -> list[bytes]:
    """Split audio into count equal-duration segments."""
    if count < 2:
        raise AudioConversionError("count must be >= 2")
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    in_path = write_temp_input(raw_bytes, original_filename)
    out_paths: list[str] = []
    try:
        proc = subprocess.run(
            [
                "ffprobe", "-v", "quiet",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                in_path,
            ],
            capture_output=True,
            timeout=60,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.decode("utf-8", errors="replace").strip()
            raise AudioConversionError(
                f"ffprobe failed: {stderr or 'unknown error'}"
            )
        duration = float(proc.stdout.decode().strip())
        segment_dur = duration / count
        results: list[bytes] = []
        for i in range(count):
            start = i * segment_dur
            end = (i + 1) * segment_dur
            out_fd, out_path = tempfile.mkstemp(
                prefix=f"audiolla-split{i}-"
            )
            os.close(out_fd)
            out_paths.append(out_path)
            _run_ffmpeg(
                [
                    "ffmpeg", "-y",
                    "-ss", str(start), "-to", str(end),
                    "-i", in_path,
                ]
                + codec_args
                + [out_path]
            )
            with open(out_path, "rb") as fh:
                results.append(fh.read())
        return results
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)
        for p in out_paths:
            if os.path.exists(p):
                os.unlink(p)


def pan_audio(
    raw_bytes: bytes,
    original_filename: str,
    output_format: str,
    position: float = 0.0,
) -> bytes:
    """Pan audio in the stereo field. position: -1.0=hard left, 1.0=hard right."""
    if not (-1.0 <= position <= 1.0):
        raise AudioConversionError(
            f"position must be in [-1.0, 1.0], got {position}"
        )
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    l_gain = (1.0 - position) / 2.0
    r_gain = (1.0 + position) / 2.0
    pan_filter = (
        f"aformat=channel_layouts=stereo,"
        f"pan=stereo|c0={l_gain}*c0+{l_gain}*c1|c1={r_gain}*c0+{r_gain}*c1"
    )
    in_path = write_temp_input(raw_bytes, original_filename)
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-pan-")
    os.close(out_fd)
    try:
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", in_path, "-af", pan_filter]
            + codec_args
            + [out_path]
        )
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def eq_audio(
    raw_bytes: bytes,
    original_filename: str,
    output_format: str,
    bands: list[dict],
) -> bytes:
    """Apply parametric EQ via ffmpeg equalizer filter.

    Each band: {"freq": Hz, "gain_db": dB, "width_hz": Hz (optional, default 100)}.
    """
    if len(bands) < 1:
        raise AudioConversionError("bands must contain at least one entry")
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    filter_parts: list[str] = []
    for i, band in enumerate(bands):
        freq = band.get("freq")
        gain_db = band.get("gain_db")
        width_hz = band.get("width_hz", 100)
        if freq is None or not (float(freq) > 0):
            raise AudioConversionError(f"band {i}: freq must be > 0")
        if gain_db is None or not (-30 <= float(gain_db) <= 30):
            raise AudioConversionError(
                f"band {i}: gain_db must be in [-30, 30]"
            )
        if not (float(width_hz) > 0):
            raise AudioConversionError(f"band {i}: width_hz must be > 0")
        filter_parts.append(
            f"equalizer=f={float(freq)}:g={float(gain_db)}"
            f":w={float(width_hz)}:t=h"
        )
    eq_filter = ",".join(filter_parts)
    in_path = write_temp_input(raw_bytes, original_filename)
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-eq-")
    os.close(out_fd)
    try:
        _run_ffmpeg(
            ["ffmpeg", "-y", "-i", in_path, "-af", eq_filter]
            + codec_args
            + [out_path]
        )
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


# ═══════════════════════════════════════════════════════════════════════════
# DYNAMICS — sidechain_duck, transient_shape, multiband_compress, deess
# ═══════════════════════════════════════════════════════════════════════════


def sidechain_duck(
    raw_bytes: bytes,
    original_filename: str,
    trigger_bytes: bytes,
    trigger_filename: str,
    output_format: str,
    threshold_db: float = -20.0,
    ratio: float = 4.0,
    attack_ms: float = 10.0,
    release_ms: float = 200.0,
) -> bytes:
    """Duck primary audio when trigger audio is loud (voiceover-over-music effect)."""
    if threshold_db > 0:
        raise AudioConversionError("threshold_db must be <= 0")
    if ratio < 1.0:
        raise AudioConversionError("ratio must be >= 1.0")
    if attack_ms <= 0:
        raise AudioConversionError("attack_ms must be > 0")
    if release_ms <= 0:
        raise AudioConversionError("release_ms must be > 0")
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    codec_args = _FORMAT_FFMPEG_CODEC[output_format]
    threshold = 10 ** (threshold_db / 20.0)
    primary_path = write_temp_input(raw_bytes, original_filename)
    trigger_path = write_temp_input(trigger_bytes, trigger_filename)
    out_fd, out_path = tempfile.mkstemp(prefix="audiolla-duck-")
    os.close(out_fd)
    try:
        filter_complex = (
            f"[0:a][1:a]sidechaincompress="
            f"threshold={threshold}:ratio={ratio}"
            f":attack={attack_ms}:release={release_ms}[out]"
        )
        cmd = [
            "ffmpeg", "-y",
            "-i", primary_path,
            "-i", trigger_path,
            "-filter_complex", filter_complex,
            "-map", "[out]",
        ]
        cmd += codec_args
        cmd.append(out_path)
        _run_ffmpeg(cmd)
        with open(out_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(primary_path):
            os.unlink(primary_path)
        if os.path.exists(trigger_path):
            os.unlink(trigger_path)
        if os.path.exists(out_path):
            os.unlink(out_path)


def _run_ffmpeg(args: list[str]) -> None:
    proc = subprocess.run(args, capture_output=True, timeout=600)
    if proc.returncode != 0:
        stderr = proc.stderr.decode("utf-8", errors="replace").strip()
        raise AudioConversionError(f"ffmpeg failed: {stderr or 'unknown error'}")


# ═══════════════════════════════════════════════════════════════════════════
# RESTORE — clip_detect, repair_audio
# ═══════════════════════════════════════════════════════════════════════════


def clip_detect(raw: bytes, filename: str) -> dict:
    """Detect digital clipping in audio.

    Returns clip stats: clipped flag, clip_count, clip_ratio, peak_db,
    duration_sec, sample_rate, channels.
    """
    import numpy as np
    import soundfile as sf

    in_path = write_temp_input(raw, filename)
    try:
        wav_path = None
        wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-clip-", suffix=".wav")
        os.close(wav_fd)
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", in_path,
            "-c:a", "pcm_f32le", wav_path,
        ])
        data, sr = sf.read(wav_path, dtype="float32", always_2d=True)
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)
        if wav_path and os.path.exists(wav_path):
            os.unlink(wav_path)

    total_samples = data.size
    clipped_mask = np.abs(data) >= 0.999
    clip_count = int(np.sum(clipped_mask))
    peak = float(np.max(np.abs(data))) if total_samples > 0 else 0.0
    peak_db = 20.0 * np.log10(peak) if peak > 0 else -96.0
    duration_sec = data.shape[0] / sr if sr > 0 else 0.0
    channels = data.shape[1] if data.ndim > 1 else 1

    return {
        "clipped": clip_count > 0,
        "clip_count": clip_count,
        "clip_ratio": round(clip_count / max(total_samples, 1), 6),
        "peak_db": round(float(peak_db), 2),
        "duration_sec": round(duration_sec, 6),
        "sample_rate": int(sr),
        "channels": channels,
    }


# ═══════════════════════════════════════════════════════════════════════════
# STEREO — mid_side_encode/decode, stereo_field (also see stereo_field below)
# ═══════════════════════════════════════════════════════════════════════════


def mid_side_encode(raw: bytes, filename: str, output_format: str = "wav") -> bytes:
    """Encode stereo audio to Mid/Side representation. Left=M, Right=S."""
    import numpy as np
    import soundfile as sf

    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )

    in_path = write_temp_input(raw, filename)
    wav_path = None
    out_wav_path = None
    try:
        wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-ms-", suffix=".wav")
        os.close(wav_fd)
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", in_path,
            "-ac", "2", "-c:a", "pcm_f32le", wav_path,
        ])
        data, sr = sf.read(wav_path, dtype="float32", always_2d=True)
        if data.shape[1] < 2:
            raise AudioConversionError(
                "mid_side_encode requires stereo audio; got mono"
            )
        L = data[:, 0]
        R = data[:, 1]
        M = (L + R) / 2.0
        S = (L - R) / 2.0
        ms_data = np.stack([M, S], axis=1)
        out_wav_fd, out_wav_path = tempfile.mkstemp(
            prefix="audiolla-ms-out-", suffix=".wav"
        )
        os.close(out_wav_fd)
        sf.write(out_wav_path, ms_data, sr, subtype="FLOAT")
        out_bytes, _ = encode_audio(out_wav_path, output_format)
        return out_bytes
    finally:
        for p in (in_path, wav_path, out_wav_path):
            if p and os.path.exists(p):
                os.unlink(p)


def mid_side_decode(raw: bytes, filename: str, output_format: str = "wav") -> bytes:
    """Decode Mid/Side audio back to stereo L/R."""
    import numpy as np
    import soundfile as sf

    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )

    in_path = write_temp_input(raw, filename)
    wav_path = None
    out_wav_path = None
    try:
        wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-msd-", suffix=".wav")
        os.close(wav_fd)
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", in_path,
            "-ac", "2", "-c:a", "pcm_f32le", wav_path,
        ])
        data, sr = sf.read(wav_path, dtype="float32", always_2d=True)
        if data.shape[1] < 2:
            raise AudioConversionError(
                "mid_side_decode requires stereo audio; got mono"
            )
        M = data[:, 0]
        S = data[:, 1]
        L = M + S
        R = M - S
        lr_data = np.stack([L, R], axis=1)
        out_wav_fd, out_wav_path = tempfile.mkstemp(
            prefix="audiolla-msd-out-", suffix=".wav"
        )
        os.close(out_wav_fd)
        sf.write(out_wav_path, lr_data, sr, subtype="FLOAT")
        out_bytes, _ = encode_audio(out_wav_path, output_format)
        return out_bytes
    finally:
        for p in (in_path, wav_path, out_wav_path):
            if p and os.path.exists(p):
                os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════
# EFFECTS — beat_slice, conv_reverb
# ═══════════════════════════════════════════════════════════════════════════


def beat_slice(
    raw: bytes, filename: str, beats: list[float], output_format: str = "wav"
) -> bytes:
    """Slice audio at beat timestamps and return a ZIP of segments.

    Segment files are named beat_001.<fmt>, beat_002.<fmt>, etc.
    """
    import soundfile as sf

    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    if len(beats) < 1:
        raise AudioConversionError("beats must contain at least one timestamp")

    in_path = write_temp_input(raw, filename)
    wav_path = None
    try:
        wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-bslice-", suffix=".wav")
        os.close(wav_fd)
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", in_path, "-c:a", "pcm_f32le", wav_path,
        ])
        data, sr = sf.read(wav_path, dtype="float32", always_2d=True)
    finally:
        for p in (in_path, wav_path):
            if p and os.path.exists(p):
                os.unlink(p)

    total_frames = data.shape[0]
    sorted_beats = sorted(beats)
    boundaries = sorted_beats + [total_frames / sr]

    segments: dict[str, bytes] = {}
    for i in range(len(sorted_beats)):
        start_frame = int(sorted_beats[i] * sr)
        end_frame = int(boundaries[i + 1] * sr)
        start_frame = max(0, min(start_frame, total_frames))
        end_frame = max(start_frame, min(end_frame, total_frames))

        seg_data = data[start_frame:end_frame]
        if seg_data.shape[0] == 0:
            continue

        seg_fd, seg_path = tempfile.mkstemp(
            prefix=f"audiolla-bseg{i}-", suffix=".wav"
        )
        os.close(seg_fd)
        try:
            sf.write(seg_path, seg_data, sr, subtype="FLOAT")
            seg_bytes, _ = encode_audio(seg_path, output_format)
        finally:
            if os.path.exists(seg_path):
                os.unlink(seg_path)

        segments[f"beat_{i + 1:03d}"] = seg_bytes

    return multi_stream_zip(segments, output_format)


def conv_reverb(
    raw: bytes,
    filename: str,
    ir_raw: bytes,
    ir_filename: str,
    *,
    wet_mix: float = 0.3,
    output_format: str = "wav",
) -> bytes:
    """Apply convolution reverb using an impulse response file.

    wet_mix: 0.0 = dry only, 1.0 = wet only.
    """
    import soundfile as sf

    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    if not (0.0 <= wet_mix <= 1.0):
        raise AudioConversionError(
            f"wet_mix must be in [0.0, 1.0], got {wet_mix}"
        )

    try:
        import pedalboard
    except ImportError as exc:
        raise AudioConversionError(
            "pedalboard is not installed; cannot run conv_reverb"
        ) from exc

    in_path = write_temp_input(raw, filename)
    ir_path = write_temp_input(ir_raw, ir_filename)
    wav_path = None
    ir_wav_path = None
    out_wav_path = None
    try:
        wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-cverb-", suffix=".wav")
        os.close(wav_fd)
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", in_path, "-c:a", "pcm_f32le", wav_path,
        ])
        ir_wav_fd, ir_wav_path = tempfile.mkstemp(
            prefix="audiolla-cverb-ir-", suffix=".wav"
        )
        os.close(ir_wav_fd)
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", ir_path, "-c:a", "pcm_f32le", ir_wav_path,
        ])

        data, sr = sf.read(wav_path, dtype="float32", always_2d=True)
        board = pedalboard.Pedalboard([
            pedalboard.Convolution(ir_wav_path, mix=wet_mix),
        ])
        processed = board(data.T, sr).T

        out_wav_fd, out_wav_path = tempfile.mkstemp(
            prefix="audiolla-cverb-out-", suffix=".wav"
        )
        os.close(out_wav_fd)
        sf.write(out_wav_path, processed, sr, subtype="FLOAT")
        out_bytes, _ = encode_audio(out_wav_path, output_format)
        return out_bytes
    finally:
        for p in (in_path, ir_path, wav_path, ir_wav_path, out_wav_path):
            if p and os.path.exists(p):
                os.unlink(p)


def transient_shape(
    raw: bytes,
    filename: str,
    *,
    attack_gain_db: float = 0.0,
    sustain_gain_db: float = 0.0,
    output_format: str = "wav",
) -> bytes:
    """Shape transients via fast-attack/slow-attack compressor blending.

    attack_gain_db > 0: boost transients (more punch).
    attack_gain_db < 0: suppress transients (more compressed).
    sustain_gain_db applies a gain to the sustain envelope.
    """
    import soundfile as sf

    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )

    try:
        import pedalboard
    except ImportError as exc:
        raise AudioConversionError(
            "pedalboard is not installed; cannot run transient_shape"
        ) from exc

    in_path = write_temp_input(raw, filename)
    wav_path = None
    out_wav_path = None
    try:
        wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-trans-", suffix=".wav")
        os.close(wav_fd)
        _run_ffmpeg([
            "ffmpeg", "-y", "-i", in_path, "-c:a", "pcm_f32le", wav_path,
        ])
        data, sr = sf.read(wav_path, dtype="float32", always_2d=True)

        attack_linear = 10 ** (attack_gain_db / 20.0)
        sustain_linear = 10 ** (sustain_gain_db / 20.0)

        if attack_gain_db < 0:
            board = pedalboard.Pedalboard([
                pedalboard.Compressor(
                    threshold_db=-20.0,
                    ratio=abs(attack_gain_db) + 1.0,
                    attack_ms=1.0,
                    release_ms=100.0,
                ),
            ])
            processed = board(data.T, sr).T
        else:
            fast_board = pedalboard.Pedalboard([
                pedalboard.Compressor(
                    threshold_db=-30.0,
                    ratio=2.0,
                    attack_ms=100.0,
                    release_ms=300.0,
                ),
            ])
            sustain_component = fast_board(data.T, sr).T
            transient_component = data - sustain_component
            processed = (
                transient_component * attack_linear
                + sustain_component * sustain_linear
            )

        out_wav_fd, out_wav_path = tempfile.mkstemp(
            prefix="audiolla-trans-out-", suffix=".wav"
        )
        os.close(out_wav_fd)
        sf.write(out_wav_path, processed, sr, subtype="FLOAT")
        out_bytes, _ = encode_audio(out_wav_path, output_format)
        return out_bytes
    finally:
        for p in (in_path, wav_path, out_wav_path):
            if p and os.path.exists(p):
                os.unlink(p)


def multiband_compress(
    raw: bytes,
    filename: str,
    *,
    crossovers_hz: list[float],
    bands: list[dict],
    output_format: str = "wav",
) -> bytes:
    """Multiband compression — split into N+1 bands at the given crossovers,
    compress each band independently, sum bands back.

    crossovers_hz: ascending list of crossover frequencies in Hz, length N.
    bands: list of N+1 band dicts with compressor params:
        threshold_db (required), ratio (required),
        attack_ms (default 10), release_ms (default 100),
        makeup_db (default 0.0).

    Bands are split with zero-phase 4th-order Butterworth (LR4-equivalent
    via sosfiltfilt double-pass) — phase-flat reconstruction, no allpass
    artifacts at the crossovers when bypassed.
    """
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    if not isinstance(crossovers_hz, list) or not crossovers_hz:
        raise AudioConversionError(
            "crossovers_hz must be a non-empty list of ascending frequencies"
        )
    if not isinstance(bands, list) or len(bands) != len(crossovers_hz) + 1:
        raise AudioConversionError(
            f"bands must have length len(crossovers_hz)+1 "
            f"({len(crossovers_hz) + 1}), got {len(bands) if isinstance(bands, list) else type(bands).__name__}"
        )
    xo = sorted(float(f) for f in crossovers_hz)
    for i, f in enumerate(xo):
        if f <= 0:
            raise AudioConversionError(
                f"crossovers_hz[{i}] must be > 0 Hz, got {f}"
            )

    import numpy as np  # noqa: PLC0415
    import soundfile as sf  # noqa: PLC0415
    from scipy.signal import butter, sosfiltfilt  # noqa: PLC0415
    try:
        import pedalboard  # noqa: PLC0415
    except ImportError as exc:
        raise AudioConversionError(
            "pedalboard is not installed; cannot run multiband_compress"
        ) from exc

    in_path = write_temp_input(raw, filename)
    wav_path = None
    out_wav_path = None
    try:
        wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-mbc-", suffix=".wav")
        os.close(wav_fd)
        _run_ffmpeg(["ffmpeg", "-y", "-i", in_path, "-c:a", "pcm_f32le", wav_path])
        data, sr = sf.read(wav_path, dtype="float32", always_2d=True)

        nyq = sr / 2.0
        for i, f in enumerate(xo):
            if f >= nyq:
                raise AudioConversionError(
                    f"crossovers_hz[{i}]={f} >= nyquist {nyq}; "
                    f"file sample rate is {sr}"
                )

        # Split into len(xo)+1 bands using cascaded LP/HP butterworth + zero-phase.
        # band[0] = LP(xo[0]); band[i] = HP(xo[i-1]) THEN LP(xo[i]); band[-1] = HP(xo[-1])
        band_signals: list = []
        for i in range(len(xo) + 1):
            sig = data
            if i > 0:
                sos_hp = butter(2, xo[i - 1] / nyq, btype="highpass", output="sos")
                sig = sosfiltfilt(sos_hp, sig, axis=0)
            if i < len(xo):
                sos_lp = butter(2, xo[i] / nyq, btype="lowpass", output="sos")
                sig = sosfiltfilt(sos_lp, sig, axis=0)
            band_signals.append(np.ascontiguousarray(sig, dtype=np.float32))

        # Per-band compression
        compressed: list = []
        for i, (sig, band) in enumerate(zip(band_signals, bands)):
            if not isinstance(band, dict):
                raise AudioConversionError(
                    f"bands[{i}] must be an object, got {type(band).__name__}"
                )
            try:
                thr = float(band["threshold_db"])
                ratio = float(band["ratio"])
            except KeyError as exc:
                raise AudioConversionError(
                    f"bands[{i}] missing required field: {exc.args[0]}"
                ) from exc
            attack = float(band.get("attack_ms", 10.0))
            release = float(band.get("release_ms", 100.0))
            makeup_db = float(band.get("makeup_db", 0.0))
            board = pedalboard.Pedalboard([
                pedalboard.Compressor(
                    threshold_db=thr, ratio=ratio,
                    attack_ms=attack, release_ms=release,
                )
            ])
            out = board(sig.T, sr).T
            if makeup_db != 0.0:
                out = out * (10.0 ** (makeup_db / 20.0))
            compressed.append(out)

        summed = np.sum(compressed, axis=0).astype(np.float32)
        np.clip(summed, -1.0, 1.0, out=summed)

        out_wav_fd, out_wav_path = tempfile.mkstemp(
            prefix="audiolla-mbc-out-", suffix=".wav"
        )
        os.close(out_wav_fd)
        sf.write(out_wav_path, summed, sr, subtype="FLOAT")
        out_bytes, _ = encode_audio(out_wav_path, output_format)
        return out_bytes
    finally:
        for p in (in_path, wav_path, out_wav_path):
            if p and os.path.exists(p):
                os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════
# ANALYZE — loudness_curve, stereo_field (defined further below)
# ═══════════════════════════════════════════════════════════════════════════


def loudness_curve(raw: bytes, filename: str, *, hop_length: int = 512) -> dict:
    """Compute RMS envelope as a loudness curve over time.
    Returns {curve: [{time_sec, rms_db}, ...], duration, sample_rate, hop_length}."""
    import librosa
    import numpy as np

    in_path = write_temp_input(raw, filename)
    wav_path = None
    try:
        wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-lc-", suffix=".wav")
        os.close(wav_fd)
        _run_ffmpeg(["ffmpeg", "-y", "-i", in_path, "-c:a", "pcm_f32le", wav_path])
        y, sr = librosa.load(wav_path, sr=None, mono=True)
        rms = librosa.feature.rms(y=y, hop_length=hop_length)[0]
        times = librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=hop_length)
        curve = []
        for t, r in zip(times.tolist(), rms.tolist()):
            db = 20.0 * np.log10(max(float(r), 1e-10))
            curve.append({"time_sec": round(float(t), 4), "rms_db": round(db, 2)})
        return {
            "curve": curve,
            "duration": round(float(len(y) / sr), 6),
            "sample_rate": int(sr),
            "hop_length": hop_length,
            "points": len(curve),
        }
    finally:
        for p in (in_path, wav_path):
            if p and os.path.exists(p):
                os.unlink(p)


def repair_audio(
    raw: bytes,
    filename: str,
    *,
    declip: bool = True,
    dehum: bool = False,
    hum_freq: float = 50.0,
    output_format: str = "wav",
) -> bytes:
    """Repair audio artifacts: declip (interpolate clipped samples) and/or dehum (notch filter).

    declip: interpolate samples that hit digital full-scale (±0.999).
    dehum: notch-filter at hum_freq and first 3 harmonics.
    hum_freq: fundamental hum frequency in Hz (50 for EU, 60 for US mains).
    """
    import numpy as np
    import soundfile as sf

    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )
    if not (40.0 <= hum_freq <= 80.0):
        raise AudioConversionError(
            f"hum_freq must be in [40, 80] Hz, got {hum_freq}"
        )
    if not declip and not dehum:
        raise AudioConversionError("at least one of declip or dehum must be True")

    in_path = write_temp_input(raw, filename)
    wav_path = None
    out_wav_path = None
    try:
        wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-repair-", suffix=".wav")
        os.close(wav_fd)
        _run_ffmpeg(["ffmpeg", "-y", "-i", in_path, "-c:a", "pcm_f32le", wav_path])
        data, sr = sf.read(wav_path, dtype="float32", always_2d=True)

        if dehum:
            from scipy.signal import iirnotch, sosfilt, tf2sos  # noqa: PLC0415
            for harmonic in range(1, 5):
                freq = hum_freq * harmonic
                if freq >= sr / 2:
                    break
                Q = 30.0
                b, a = iirnotch(freq / (sr / 2), Q)
                sos = tf2sos(b, a)
                for ch in range(data.shape[1]):
                    data[:, ch] = sosfilt(sos, data[:, ch]).astype(np.float32)

        if declip:
            THRESHOLD = 0.999
            for ch in range(data.shape[1]):
                col = data[:, ch].copy()
                clipped = np.abs(col) >= THRESHOLD
                if not np.any(clipped):
                    continue
                indices = np.arange(len(col))
                good = ~clipped
                if np.sum(good) < 2:
                    continue
                col[clipped] = np.interp(
                    indices[clipped], indices[good], col[good]
                )
                data[:, ch] = col

        out_wav_fd, out_wav_path = tempfile.mkstemp(
            prefix="audiolla-repair-out-", suffix=".wav"
        )
        os.close(out_wav_fd)
        sf.write(out_wav_path, data, sr, subtype="FLOAT")
        out_bytes, _ = encode_audio(out_wav_path, output_format)
        return out_bytes
    finally:
        for p in (in_path, wav_path, out_wav_path):
            if p and os.path.exists(p):
                os.unlink(p)


# ═══════════════════════════════════════════════════════════════════════════
# MIDI — chords_to_midi_bytes (and other tiny MIDI helpers)
# ═══════════════════════════════════════════════════════════════════════════


def chords_to_midi_bytes(
    chords: list[dict],
    *,
    tempo_bpm: float = 120.0,
    velocity: int = 80,
    octave: int = 4,
) -> bytes:
    """Convert chord segments to a Type-1 MIDI file.

    chords: [{"chord": "C major", "start_sec": 0.0, "end_sec": 2.0}, ...]
    Each chord maps to root + third + fifth. Returns MIDI bytes.
    """
    import io

    import mido

    _NOTE_MAP = {
        "C": 0, "C#": 1, "D": 2, "D#": 3, "E": 4, "F": 5,
        "F#": 6, "G": 7, "G#": 8, "A": 9, "A#": 10, "B": 11,
    }

    def _chord_notes(chord_name: str, oct: int) -> list[int]:
        parts = chord_name.strip().split()
        if len(parts) < 2:
            return []
        root_pc = _NOTE_MAP.get(parts[0])
        if root_pc is None:
            return []
        base = 12 * (oct + 1) + root_pc
        quality = parts[1].lower()
        if quality == "major":
            return [base, base + 4, base + 7]
        return [base, base + 3, base + 7]

    if not (1.0 <= tempo_bpm <= 999.0):
        raise AudioConversionError(f"tempo_bpm must be in [1, 999], got {tempo_bpm}")
    if not (1 <= velocity <= 127):
        raise AudioConversionError(f"velocity must be in [1, 127], got {velocity}")
    if not (1 <= octave <= 7):
        raise AudioConversionError(f"octave must be in [1, 7], got {octave}")

    tpb = 480
    seconds_per_tick = 60.0 / tempo_bpm / tpb

    mid = mido.MidiFile(type=1, ticks_per_beat=tpb)
    tempo_track = mido.MidiTrack()
    tempo_track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(tempo_bpm), time=0))
    mid.tracks.append(tempo_track)

    chord_track = mido.MidiTrack()
    chord_track.append(mido.Message("program_change", channel=0, program=0, time=0))
    events: list[tuple[int, object]] = []

    for seg in chords:
        chord_name = seg.get("chord", "")
        start_sec = float(seg.get("start_sec", 0.0))
        end_sec = float(seg.get("end_sec", start_sec + 1.0))
        notes = _chord_notes(chord_name, octave)
        if not notes:
            continue
        on_tick = int(round(start_sec / seconds_per_tick))
        off_tick = int(round(end_sec / seconds_per_tick))
        if off_tick <= on_tick:
            off_tick = on_tick + tpb
        for note in notes:
            if 0 <= note <= 127:
                events.append((on_tick, mido.Message(
                    "note_on", channel=0, note=note, velocity=velocity, time=0,
                )))
                events.append((off_tick, mido.Message(
                    "note_off", channel=0, note=note, velocity=0, time=0,
                )))

    events.sort(key=lambda x: (x[0], 0 if x[1].type == "note_off" else 1))
    prev = 0
    for tick, msg in events:
        msg.time = tick - prev
        chord_track.append(msg)
        prev = tick
    mid.tracks.append(chord_track)

    buf = io.BytesIO()
    mid.save(file=buf)
    return buf.getvalue()


def deess(
    raw: bytes,
    filename: str,
    *,
    threshold_db: float = -20.0,
    frequency_hz: float = 6000.0,
    ratio: float = 4.0,
    output_format: str = "wav",
) -> bytes:
    """Split-band de-esser: detect sibilance above frequency_hz and compress it.

    threshold_db: sibilance level above which compression kicks in (dBFS).
    frequency_hz: highpass cutoff that isolates the sibilance band (Hz).
    ratio: compression ratio applied to the sibilance band.
    """
    import numpy as np
    import soundfile as sf
    from scipy.signal import butter, sosfilt, lfilter  # noqa: PLC0415

    if not (1.0 <= ratio <= 50.0):
        raise AudioConversionError(f"ratio must be in [1.0, 50.0], got {ratio}")
    if not (1000.0 <= frequency_hz <= 16000.0):
        raise AudioConversionError(
            f"frequency_hz must be in [1000, 16000], got {frequency_hz}"
        )
    if output_format not in SUPPORTED_OUTPUT_FORMATS:
        raise AudioConversionError(
            f"unsupported output format {output_format!r}; "
            f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
        )

    in_path = write_temp_input(raw, filename)
    wav_path = None
    out_wav_path = None
    try:
        wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-deess-", suffix=".wav")
        os.close(wav_fd)
        _run_ffmpeg(["ffmpeg", "-y", "-i", in_path, "-c:a", "pcm_f32le", wav_path])
        data, sr = sf.read(wav_path, dtype="float32", always_2d=True)

        nyq = sr / 2.0
        freq_norm = min(frequency_hz / nyq, 0.99)
        sos = butter(4, freq_norm, btype="high", output="sos")

        threshold_lin = 10.0 ** (threshold_db / 20.0)
        t_smooth = 0.010
        a = float(np.exp(-1.0 / (sr * t_smooth)))

        result = data.copy()
        for ch in range(data.shape[1]):
            col = data[:, ch].astype(np.float64)
            high = sosfilt(sos, col)
            env = lfilter([1.0 - a], [1.0, -a], np.abs(high))
            gain = np.ones_like(env)
            mask = env > threshold_lin
            if np.any(mask):
                compressed = threshold_lin + (env[mask] - threshold_lin) / ratio
                gain[mask] = compressed / env[mask]
            result[:, ch] = (col - high + high * gain).astype(np.float32)

        out_wav_fd, out_wav_path = tempfile.mkstemp(
            prefix="audiolla-deess-out-", suffix=".wav"
        )
        os.close(out_wav_fd)
        sf.write(out_wav_path, result, sr, subtype="FLOAT")
        out_bytes, _ = encode_audio(out_wav_path, output_format)
        return out_bytes
    finally:
        for p in (in_path, wav_path, out_wav_path):
            if p and os.path.exists(p):
                os.unlink(p)


def stereo_field(raw: bytes, filename: str) -> dict:
    """Analyse the stereo field: correlation, width, balance, mono compatibility.

    Returns a dict with correlation (-1..1), width (0=mono, 1=normal stereo),
    balance_db (positive = L louder), mid/side levels, and diagnostic flags.
    """
    import numpy as np
    import soundfile as sf

    in_path = write_temp_input(raw, filename)
    wav_path = None
    try:
        wav_fd, wav_path = tempfile.mkstemp(
            prefix="audiolla-stereofield-", suffix=".wav"
        )
        os.close(wav_fd)
        _run_ffmpeg(["ffmpeg", "-y", "-i", in_path, "-c:a", "pcm_f32le", wav_path])
        data, sr = sf.read(wav_path, dtype="float32", always_2d=True)
        duration = round(float(len(data) / sr), 4)

        if data.shape[1] == 1:
            rms_db = round(float(20.0 * np.log10(
                float(np.sqrt(np.mean(data[:, 0].astype(np.float64) ** 2))) + 1e-9
            )), 2)
            return {
                "correlation": 1.0,
                "width": 0.0,
                "balance_db": 0.0,
                "mono_compatible": True,
                "mid_level_db": rms_db,
                "side_level_db": -96.0,
                "phase_issues": False,
                "channels": 1,
                "sample_rate": sr,
                "duration": duration,
            }

        L = data[:, 0].astype(np.float64)
        R = data[:, 1].astype(np.float64)

        lc = L - float(np.mean(L))
        rc = R - float(np.mean(R))
        norm = float(np.linalg.norm(lc)) * float(np.linalg.norm(rc))
        correlation = round(float(np.dot(lc, rc) / norm) if norm > 0.0 else 1.0, 4)

        mid = (L + R) * 0.5
        side = (L - R) * 0.5

        mid_rms = float(np.sqrt(np.mean(mid ** 2))) + 1e-9
        side_rms = float(np.sqrt(np.mean(side ** 2))) + 1e-9
        l_rms = float(np.sqrt(np.mean(L ** 2))) + 1e-9
        r_rms = float(np.sqrt(np.mean(R ** 2))) + 1e-9

        width = round(side_rms / mid_rms, 4)
        balance_db = round(float(20.0 * np.log10(l_rms / r_rms)), 2)
        mid_db = round(float(20.0 * np.log10(mid_rms)), 2)
        side_db = round(float(20.0 * np.log10(side_rms)), 2)

        return {
            "correlation": correlation,
            "width": width,
            "balance_db": balance_db,
            "mono_compatible": correlation >= 0.5,
            "mid_level_db": mid_db,
            "side_level_db": side_db,
            "phase_issues": correlation < 0.0,
            "channels": int(data.shape[1]),
            "sample_rate": int(sr),
            "duration": duration,
        }
    finally:
        for p in (in_path, wav_path):
            if p and os.path.exists(p):
                os.unlink(p)


def multi_stream_zip(
    streams: dict[str, bytes], output_format: str
) -> bytes:
    """Pack multiple audio streams into a single zip blob.

    Used by ``/v1/audio/separate`` when more than one stem is requested.
    The zip member names follow ``<stem_name>.<output_format>`` (e.g.
    ``vocals.wav``, ``drums.wav``). DEFLATE-compressed so a 4-stem WAV
    bundle of 4×1.4 MB compresses to ~700 KB.
    """
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for stem_name, audio_bytes in streams.items():
            zf.writestr(f"{stem_name}.{output_format}", audio_bytes)
    return buf.getvalue()
