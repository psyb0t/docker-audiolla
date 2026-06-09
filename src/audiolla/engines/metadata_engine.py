"""Audio metadata engine — read/write ID3, Vorbis, FLAC, and generic audio tags via mutagen.

No ML weights. get_model() returns a sentinel string; loaded() is always False.
mutagen is imported lazily so that import errors surface only at runtime.
"""

from __future__ import annotations

import asyncio
import logging
import os
import tempfile
import time

from ..audio import AudioConversionError, encode_audio, write_temp_input
from .base import EngineBase

_log = logging.getLogger("audiolla.engine.metadata")

_SENTINEL = "metadata-engine-no-model"

_TAG_MAP_ID3 = {
    "title": "TIT2",
    "artist": "TPE1",
    "album": "TALB",
    "genre": "TCON",
    "year": "TDRC",
    "comment": "COMM::eng",
    "track_number": "TRCK",
    "bpm": "TBPM",
    "key": "TKEY",
    "encoder": "TENC",
}

_TAG_MAP_VORBIS = {
    "title": "title",
    "artist": "artist",
    "album": "album",
    "genre": "genre",
    "year": "date",
    "comment": "comment",
    "track_number": "tracknumber",
    "bpm": "bpm",
    "key": "key",
    "encoder": "encoder",
}


def _import_mutagen():
    try:
        import mutagen
        return mutagen
    except ImportError as exc:
        _log.exception("mutagen import failed")
        raise AudioConversionError(
            "mutagen is not installed; add it to the image"
        ) from exc


def _read_tags_sync(raw: bytes, filename: str) -> dict:
    _import_mutagen()
    from mutagen import File as MFile

    in_path = write_temp_input(raw, filename)
    try:
        mf = MFile(in_path)
        if mf is None:
            _log.warning("mutagen could not parse %r", filename)
            raise AudioConversionError(f"mutagen could not parse {filename!r}")

        raw_tags: dict = {}
        for k, v in mf.tags.items() if mf.tags else []:
            try:
                raw_tags[str(k)] = str(v)
            except Exception:
                raw_tags[str(k)] = repr(v)

        def _get(field: str) -> str:
            val = mf.tags.get(field) if mf.tags else None
            if val is None:
                return ""
            return str(val)

        info = mf.info if hasattr(mf, "info") else None
        duration_sec = float(getattr(info, "length", 0.0)) if info else 0.0
        sample_rate = int(getattr(info, "sample_rate", 0)) if info else 0
        channels = int(getattr(info, "channels", 0)) if info else 0

        is_id3 = hasattr(mf, "tags") and mf.tags is not None and hasattr(mf.tags, "getall")

        if is_id3:
            def _id3(frame_id: str) -> str:
                frames = mf.tags.getall(frame_id)
                if not frames:
                    return ""
                return str(frames[0])
            result = {
                "title": _id3("TIT2"),
                "artist": _id3("TPE1"),
                "album": _id3("TALB"),
                "genre": _id3("TCON"),
                "year": _id3("TDRC"),
                "comment": _id3("COMM::eng") or _id3("COMM"),
                "track_number": _id3("TRCK"),
                "bpm": _id3("TBPM"),
                "key": _id3("TKEY"),
                "encoder": _id3("TENC"),
                "duration_sec": duration_sec,
                "sample_rate": sample_rate,
                "channels": channels,
                "raw_tags": raw_tags,
            }
        else:
            result = {
                "title": _get("title"),
                "artist": _get("artist"),
                "album": _get("album"),
                "genre": _get("genre"),
                "year": _get("date") or _get("year"),
                "comment": _get("comment"),
                "track_number": _get("tracknumber"),
                "bpm": _get("bpm"),
                "key": _get("key"),
                "encoder": _get("encoder"),
                "duration_sec": duration_sec,
                "sample_rate": sample_rate,
                "channels": channels,
                "raw_tags": raw_tags,
            }
        return result
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)


def _write_tags_sync(
    raw: bytes, filename: str, tags: dict, output_format: str | None
) -> bytes:
    _import_mutagen()
    from mutagen import File as MFile

    in_path = write_temp_input(raw, filename)
    try:
        mf = MFile(in_path)
        if mf is None:
            _log.warning("mutagen could not parse %r for tag write", filename)
            raise AudioConversionError(f"mutagen could not parse {filename!r}")

        if mf.tags is None:
            mf.add_tags()

        is_id3 = hasattr(mf.tags, "getall")

        if is_id3:
            import mutagen.id3 as id3_mod

            _id3_class_map = {
                "TIT2": id3_mod.TIT2,
                "TPE1": id3_mod.TPE1,
                "TALB": id3_mod.TALB,
                "TCON": id3_mod.TCON,
                "TDRC": id3_mod.TDRC,
                "TRCK": id3_mod.TRCK,
                "TBPM": id3_mod.TBPM,
                "TKEY": id3_mod.TKEY,
                "TENC": id3_mod.TENC,
            }
            for tag_name, frame_id in _TAG_MAP_ID3.items():
                val = tags.get(tag_name)
                if val is None:
                    continue
                val_str = str(val)
                if frame_id == "COMM::eng":
                    mf.tags["COMM"] = id3_mod.COMM(
                        encoding=3, lang="eng", desc="", text=[val_str]
                    )
                    continue
                cls = _id3_class_map.get(frame_id)
                if cls is None:
                    continue
                mf.tags[frame_id] = cls(encoding=3, text=[val_str])
        else:
            for tag_name, vorbis_key in _TAG_MAP_VORBIS.items():
                val = tags.get(tag_name)
                if val is None:
                    continue
                mf.tags[vorbis_key] = [str(val)]

        mf.save(in_path)

        if output_format:
            wav_fd, wav_path = tempfile.mkstemp(prefix="audiolla-meta-wav-", suffix=".wav")
            os.close(wav_fd)
            try:
                import subprocess
                proc = subprocess.run(
                    ["ffmpeg", "-y", "-i", in_path, wav_path],
                    capture_output=True, timeout=120,
                )
                if proc.returncode != 0:
                    _log.warning(
                        "ffmpeg decode failed after tag write rc=%d",
                        proc.returncode,
                    )
                    raise AudioConversionError(
                        "ffmpeg decode failed after tag write: "
                        + proc.stderr.decode("utf-8", errors="replace").strip()
                    )
                out_bytes, _ = encode_audio(wav_path, output_format)
            finally:
                if os.path.exists(wav_path):
                    os.unlink(wav_path)
            return out_bytes

        with open(in_path, "rb") as fh:
            return fh.read()
    finally:
        if os.path.exists(in_path):
            os.unlink(in_path)


class MetadataEngine(EngineBase):
    def _load_sync(self):
        return _SENTINEL

    def loaded(self) -> bool:
        return False

    async def read_tags(self, raw: bytes, filename: str) -> dict:
        _import_mutagen()
        self._log.info(
            "read_tags start: filename=%s input_bytes=%d", filename, len(raw),
        )
        t0 = time.perf_counter()
        self._touch()
        result = await asyncio.to_thread(_read_tags_sync, raw, filename)
        self._log.info(
            "read_tags done: filename=%s duration_ms=%.1f tag_keys=%d",
            filename, (time.perf_counter() - t0) * 1000.0,
            len(result.get("raw_tags", {})),
        )
        return result

    async def write_tags(
        self,
        raw: bytes,
        filename: str,
        tags: dict,
        output_format: str | None = None,
    ) -> bytes:
        _import_mutagen()
        self._log.info(
            "write_tags start: filename=%s input_bytes=%d tag_keys=%d "
            "output_format=%s",
            filename, len(raw), len(tags) if tags else 0, output_format,
        )
        t0 = time.perf_counter()
        self._touch()
        result = await asyncio.to_thread(
            _write_tags_sync, raw, filename, tags, output_format
        )
        self._log.info(
            "write_tags done: filename=%s duration_ms=%.1f output_bytes=%d",
            filename, (time.perf_counter() - t0) * 1000.0, len(result),
        )
        return result
