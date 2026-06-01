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
