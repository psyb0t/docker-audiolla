"""Audio ingress/egress helpers — ffmpeg encode/decode.

Decode any format to float32 stereo/mono WAV at the original sample rate
for processing. Encode processed audio back to the requested output format
at egress. All conversion via ffmpeg subprocess — broad codec matrix without
extra Python deps.
"""

from __future__ import annotations

import os
import subprocess
import tempfile


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
