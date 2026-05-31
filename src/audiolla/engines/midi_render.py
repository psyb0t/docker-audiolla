"""MIDI-to-audio renderer (fluidsynth subprocess, GPL v3 binary — LGPLv2.1 library).

Synthesises a MIDI file to audio using fluidsynth + a SoundFont (default
FluidR3_GM at ``/usr/share/sounds/sf2/FluidR3_GM.sf2`` from the Debian
``fluid-soundfont-gm`` package, MIT-licensed). The SoundFont path can be
overridden per request by passing a path under the staging area, or
globally via the ``AUDIOLLA_SOUNDFONT`` env var.

Subprocess invocation:

    fluidsynth -ni -F <out.wav> -r <samplerate> -g <gain> \\
        <soundfont.sf2> <input.mid>

We pin the sample rate (44.1 kHz) and gain (0.5 — fluidsynth's default
is hot and clips easily on percussive MIDI) so the output is predictable
across hosts. The resulting WAV is then transcoded to the caller's
requested ``output_format`` via the existing ``encode_audio`` helper.

No model weights — the SoundFont is loaded fresh per call (fluidsynth
caches the loaded data for the lifetime of its process, which is one
render). ``get_model()`` is a no-op. CPU-only.
"""

from __future__ import annotations

import asyncio
import os
import subprocess
import tempfile

from .. import config
from .. import files as files_mod
from ..audio import AudioConversionError, encode_audio
from .base import EngineBase


class MidiRenderError(AudioConversionError):
    """fluidsynth was missing, the SoundFont was unreadable, or the
    subprocess failed."""


class MidiRenderEngine(EngineBase):
    """Wraps fluidsynth for MIDI -> audio synthesis."""

    def __init__(self, slug: str, entry: dict) -> None:
        super().__init__(slug, entry)

    async def render(
        self,
        raw: bytes,
        filename: str,
        *,
        soundfont_path: str | None = None,
        output_format: str = "wav",
        gain: float = 0.5,
        samplerate: int = 44100,
    ) -> bytes:
        async with self._lock:
            result = await asyncio.to_thread(
                self._render_sync,
                raw, filename, soundfont_path, output_format, gain, samplerate,
            )
            self._touch()
            return result

    def _resolve_soundfont(self, override: str | None) -> str:
        """Resolve the SoundFont path. If `override` is given it's
        interpreted as a relative path under FILES_DIR — same sanitisation
        as the audio endpoints' file_path. Otherwise fall back to
        ``config.SOUNDFONT_PATH`` (which the prod images point at
        FluidR3_GM)."""
        if override:
            try:
                rel = files_mod.sanitize_path(override)
                src = files_mod.resolve_under(config.FILES_DIR, rel)
            except files_mod.FilePathError as exc:
                raise MidiRenderError(
                    f"soundfont_path {override!r}: {exc}"
                ) from exc
            if src.is_symlink() or not src.is_file():
                raise MidiRenderError(
                    f"soundfont_path not found in staging: {rel}"
                )
            return str(src)
        if not config.SOUNDFONT_PATH:
            raise MidiRenderError(
                "no default SoundFont configured — set AUDIOLLA_SOUNDFONT "
                "or pass soundfont_path on the request"
            )
        if not os.path.isfile(config.SOUNDFONT_PATH):
            raise MidiRenderError(
                f"AUDIOLLA_SOUNDFONT={config.SOUNDFONT_PATH!r} is not a file"
            )
        return config.SOUNDFONT_PATH

    def _render_sync(
        self,
        raw: bytes,
        filename: str,
        soundfont_override: str | None,
        output_format: str,
        gain: float,
        samplerate: int,
    ) -> bytes:
        if not raw:
            raise MidiRenderError("MIDI input is empty")
        if not raw.startswith(b"MThd"):
            # Standard MIDI header — quick fail before invoking fluidsynth
            # so a misuploaded WAV doesn't produce a confusing error.
            raise MidiRenderError(
                "input does not look like a Standard MIDI File (missing 'MThd')"
            )

        sf2 = self._resolve_soundfont(soundfont_override)

        if not (0.0 <= gain <= 5.0):
            raise MidiRenderError(f"gain must be in [0.0, 5.0], got {gain}")
        if samplerate not in (22050, 44100, 48000, 88200, 96000):
            raise MidiRenderError(
                f"samplerate {samplerate} unsupported (use 22050/44100/48000/88200/96000)"
            )

        mid_fd, mid_path = tempfile.mkstemp(prefix="audiolla-midi-", suffix=".mid")
        try:
            with os.fdopen(mid_fd, "wb") as fh:
                fh.write(raw)
        except Exception:
            os.close(mid_fd)
            raise

        out_fd, out_wav = tempfile.mkstemp(prefix="audiolla-midi-", suffix=".wav")
        os.close(out_fd)

        try:
            cmd = [
                "fluidsynth",
                "-ni",                # no shell, immediate exit after render
                "-F", out_wav,
                "-r", str(samplerate),
                "-g", str(gain),
                "-T", "wav",          # force WAV output (not raw)
                sf2,
                mid_path,
            ]
            try:
                proc = subprocess.run(
                    cmd,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=300,  # 5 min hard cap per render
                )
            except FileNotFoundError as exc:
                raise MidiRenderError(
                    "fluidsynth binary not found on PATH — is the prod "
                    "image being used? (Dev image doesn't ship it.)"
                ) from exc
            except subprocess.TimeoutExpired as exc:
                raise MidiRenderError(
                    "fluidsynth render exceeded 300s timeout"
                ) from exc
            if proc.returncode != 0:
                stderr = (proc.stderr or "").strip().splitlines()[-1:] or ["<no stderr>"]
                raise MidiRenderError(
                    f"fluidsynth exit={proc.returncode}: {stderr[0]}"
                )
            if not os.path.isfile(out_wav) or os.path.getsize(out_wav) == 0:
                raise MidiRenderError(
                    "fluidsynth produced no output WAV (silent MIDI?)"
                )
            audio_bytes, _ct = encode_audio(out_wav, output_format)
            return audio_bytes
        finally:
            for p in (mid_path, out_wav):
                try:
                    os.unlink(p)
                except OSError:
                    pass
