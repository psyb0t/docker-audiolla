"""MCP server for audiolla — mounted at ``/v1/mcp`` on the main FastAPI app.

Exposes the same surface as the HTTP REST API as MCP tools so an agent can
drive audiolla over JSON-RPC / streamable-HTTP. Tools:

  - ``list_engines``   — what engines are loadable
  - ``separate``       — run Demucs stem separation
  - ``master``         — matchering reference + pedalboard chain mastering
  - ``analyze``        — librosa MIR feature extraction
  - ``transform``      — pysox DSP chain
  - ``loudness``       — pyloudnorm analyze / normalize
  - ``list_files``     — what's currently staged
  - ``put_file``       — upload a file (base64-encoded body)
  - ``get_file``       — read a staged file (base64-encoded body back)
  - ``delete_file``    — remove a staged file

Input to audio tools: pass either ``file_path`` (a path in the staging area
populated via ``put_file`` or the REST ``/v1/files`` endpoints) OR
``file_url`` (a remote URL the server fetches — subject to the
``AUDIOLLA_FETCH_MODE`` allowlist/denylist policy in config). Exactly one
of the two is required.

Output from audio tools defaults to base64-encoded audio because MCP
JSON-RPC can't carry raw bytes. Pass ``output_url`` to have the server PUT
the result to a presigned URL instead (subject to the same fetch policy);
``separate`` accepts ``output_urls`` as a per-stem map.

Why a separate module: avoids a circular import between ``server.py`` (which
holds the shared ``ENGINES`` / ``REGISTRY`` state) and this module. ``server.py``
calls ``build_mcp_server(...)`` at startup and mounts the returned ASGI app
under ``/v1/mcp`` via FastMCP's streamable_http transport.
"""

from __future__ import annotations

import base64
import binascii
import logging
from typing import Any

from mcp.server.fastmcp import FastMCP

from . import config, fetch
from . import files as files_mod
import asyncio

from .audio import AudioConversionError, content_type_for, clip_detect, mid_side_encode, mid_side_decode, beat_slice, conv_reverb, transient_shape

_log = logging.getLogger("audiolla.mcp")


def build_mcp_server(
    *,
    engines: dict[str, Any],
    registry: dict[str, dict[str, Any]],
) -> FastMCP:
    """Construct the FastMCP server. Mount under ``/v1/mcp`` so clients
    connect to ``/v1/mcp`` directly (the FastMCP SDK's streamable_http_path
    is configured to ``/`` so the mount doesn't double-prefix).
    """
    mcp = FastMCP(
        name="audiolla",
        instructions=(
            "Self-hosted music-production tools: stem separation, "
            "mastering, MIR analysis, DSP transform, loudness. Three input "
            "modes for audio: stage a file via put_file (base64) then pass "
            "file_path, OR pass file_url to have the server fetch a remote "
            "URL (subject to AUDIOLLA_FETCH_MODE allowlist/denylist). "
            "Audio results default to base64; pass output_url to have the "
            "server PUT to a presigned URL instead."
        ),
        stateless_http=True,
        json_response=True,
    )
    mcp.settings.streamable_http_path = "/"

    # ── helpers ─────────────────────────────────────────────────────────────

    def _load_staged(path: str) -> tuple[bytes, str]:
        try:
            rel = files_mod.sanitize_path(path)
            src = files_mod.resolve_under(config.FILES_DIR, rel)
        except files_mod.FilePathError as exc:
            raise ValueError(str(exc)) from exc
        if src.is_symlink() or not src.is_file():
            raise ValueError(f"file not found: {rel}")
        return src.read_bytes(), str(rel)

    async def _load_input(
        file_path: str | None,
        file_url: str | None,
        *,
        field_prefix: str = "file",
    ) -> tuple[bytes, str]:
        """Resolve exactly one of (file_path, file_url) to (bytes, name)."""
        has_path = bool(file_path)
        has_url = bool(file_url)
        n = int(has_path) + int(has_url)
        if n == 0:
            raise ValueError(
                f"must provide one of {field_prefix}_path or {field_prefix}_url"
            )
        if n > 1:
            raise ValueError(
                f"provide only one of {field_prefix}_path or {field_prefix}_url"
            )
        if has_path:
            assert file_path is not None
            return _load_staged(file_path)
        assert file_url is not None
        try:
            return await fetch.fetch_to_bytes(file_url, config.MAX_UPLOAD_BYTES)
        except fetch.FetchError as exc:
            raise ValueError(str(exc)) from exc

    async def _emit_audio(
        data: bytes,
        output_format: str,
        output_url: str | None,
    ) -> dict[str, Any]:
        """Return audio either base64-encoded (default) or as a presigned-PUT
        upload confirmation when output_url is set."""
        if output_url:
            try:
                await fetch.upload_bytes(
                    output_url,
                    data,
                    content_type_for(output_format),
                )
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {
                "url": output_url,
                "size": len(data),
                "output_format": output_format,
            }
        return {
            "audio_base64": base64.b64encode(data).decode("ascii"),
            "output_format": output_format,
        }

    # ── engine discovery ────────────────────────────────────────────────────

    @mcp.tool()
    async def list_engines() -> dict[str, Any]:
        """List configured engines + their capabilities."""
        out: list[dict[str, Any]] = []
        for slug, engine in engines.items():
            entry = registry.get(slug, {})
            out.append(
                {
                    "slug": slug,
                    "executor": entry.get("executor", ""),
                    "variant": entry.get("variant"),
                    "stems": entry.get("stems"),
                    "presets": entry.get("presets"),
                    "loaded": engine.loaded(),
                }
            )
        return {"engines": out}

    # ── audio processing tools ──────────────────────────────────────────────

    @mcp.tool()
    async def separate(
        engine: str,
        stems: list[str],
        file_path: str | None = None,
        file_url: str | None = None,
        output_format: str = "wav",
        output_urls: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Demucs stem separation.

        Provide exactly one of `file_path` or `file_url`. By default the
        per-stem audio comes back base64-encoded under `stems`. Pass
        `output_urls={stem_name: presigned_put_url}` to have the server
        PUT each requested stem to its URL instead — response then has
        `uploaded_stems` mapping stem -> {url, size}.
        """
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get(engine)
        if eng is None or not hasattr(eng, "separate"):
            raise ValueError(
                f"engine {engine!r} not configured or doesn't support separation"
            )
        try:
            result = await eng.separate(
                raw, name, stems=stems, output_format=output_format
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

        if output_urls:
            missing = [s for s in result if s not in output_urls]
            if missing:
                raise ValueError(
                    f"output_urls missing entries for stem(s) {missing}; "
                    f"got keys {sorted(output_urls)}"
                )
            ct = content_type_for(output_format)
            uploaded: dict[str, dict[str, Any]] = {}
            for stem_name, audio in result.items():
                url = output_urls[stem_name]
                try:
                    await fetch.upload_bytes(url, audio, ct)
                except fetch.FetchError as exc:
                    raise ValueError(
                        f"upload of stem {stem_name!r} failed: {exc}"
                    ) from exc
                uploaded[stem_name] = {"url": url, "size": len(audio)}
            return {
                "uploaded_stems": uploaded,
                "output_format": output_format,
            }

        return {
            "stems": {
                stem_name: base64.b64encode(audio).decode("ascii")
                for stem_name, audio in result.items()
            },
            "output_format": output_format,
        }

    @mcp.tool()
    async def master(
        mode: str,
        file_path: str | None = None,
        file_url: str | None = None,
        reference_path: str | None = None,
        reference_url: str | None = None,
        preset: str | None = None,
        target_lufs: float | None = None,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Master audio.

        Provide exactly one of `file_path` or `file_url`. For
        `mode=reference`, also provide one of `reference_path` or
        `reference_url`. For `mode=chain`, set `preset` (transparent or
        loud). Returns base64 audio unless `output_url` is set (presigned
        PUT). target_lufs is optional in both modes.
        """
        if mode not in ("reference", "chain"):
            raise ValueError("mode must be 'reference' or 'chain'")
        raw, name = await _load_input(file_path, file_url)
        if mode == "reference":
            eng = engines.get("matchering")
            if eng is None:
                raise ValueError("matchering engine not configured")
            ref_raw, ref_name = await _load_input(
                reference_path,
                reference_url,
                field_prefix="reference",
            )
            try:
                audio = await eng.master_reference(
                    raw,
                    name,
                    ref_raw,
                    ref_name,
                    target_lufs=target_lufs,
                    output_format=output_format,
                )
            except AudioConversionError as exc:
                raise ValueError(str(exc)) from exc
        else:
            if not preset:
                raise ValueError("mode=chain requires preset")
            eng = engines.get("pedalboard-chain")
            if eng is None:
                raise ValueError("pedalboard-chain engine not configured")
            try:
                audio = await eng.master_chain(
                    raw,
                    name,
                    preset=preset,
                    target_lufs=target_lufs,
                    output_format=output_format,
                )
            except AudioConversionError as exc:
                raise ValueError(str(exc)) from exc
        return await _emit_audio(audio, output_format, output_url)

    @mcp.tool()
    async def analyze(
        file_path: str | None = None,
        file_url: str | None = None,
        features: list[str] | None = None,
    ) -> dict[str, Any]:
        """librosa MIR analysis. Returns extracted features as JSON.

        Provide exactly one of `file_path` or `file_url`. Valid feature
        names: bpm, key, loudness, duration, spectral_centroid, rms,
        zcr. Empty/None features means all of them.
        """
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("librosa-analyze")
        if eng is None:
            raise ValueError("librosa-analyze engine not configured")
        try:
            result = await eng.analyze(raw, name, features=features or [])
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return result

    @mcp.tool()
    async def transform(
        operations: list[dict[str, Any]],
        file_path: str | None = None,
        file_url: str | None = None,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """pysox DSP transform chain.

        Provide exactly one of `file_path` or `file_url`. `operations` is
        a list of {op, params} — valid ops: gain, equalizer, compand,
        reverb, pitch, tempo, rate, channels, trim, pad. Returns base64
        audio unless `output_url` is set (presigned PUT).
        """
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("sox-transform")
        if eng is None:
            raise ValueError("sox-transform engine not configured")
        try:
            audio = await eng.transform(
                raw,
                name,
                operations=operations,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio, output_format, output_url)

    @mcp.tool()
    async def loudness(
        file_path: str | None = None,
        file_url: str | None = None,
    ) -> dict[str, Any]:
        """Measure integrated loudness (LUFS) via pyloudnorm. Returns JSON only.
        Use ``normalize`` to produce loudness-normalized audio."""
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("librosa-analyze")
        if eng is None or not hasattr(eng, "measure_lufs"):
            raise ValueError("loudness engine not configured")
        try:
            lufs = await eng.measure_lufs(raw, name)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return {"loudness_lufs": lufs}

    @mcp.tool()
    async def normalize(
        file_path: str | None = None,
        file_url: str | None = None,
        target_lufs: float = -14.0,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Normalize audio to a target LUFS level via pyloudnorm.

        Provide exactly one of `file_path` or `file_url`. Returns base64
        audio plus ``measured_lufs`` and ``target_lufs``. Pass
        ``output_url`` for a presigned PUT instead.
        """
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("librosa-analyze")
        if eng is None or not hasattr(eng, "normalize_lufs"):
            raise ValueError("loudness engine not configured")
        try:
            audio, measured = await eng.normalize_lufs(
                raw,
                name,
                target_lufs=target_lufs,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        emitted = await _emit_audio(audio, output_format, output_url)
        emitted["measured_lufs"] = measured
        emitted["target_lufs"] = target_lufs
        return emitted

    # ── effects-chain tool ──────────────────────────────────────────────────

    @mcp.tool()
    async def fx(
        effects: list[dict[str, Any]],
        file_path: str | None = None,
        file_url: str | None = None,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Generic effects chain.

        Provide exactly one of `file_path` or `file_url`. `effects` is an
        ordered list of {type, params} — type names match pedalboard
        classes (Compressor, Reverb, Chorus, Delay, PitchShift,
        HighShelfFilter, ...). Returns base64 audio unless `output_url`
        is set (presigned PUT).
        """
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("fx-chain")
        if eng is None or not hasattr(eng, "fx"):
            raise ValueError("fx-chain engine not configured")
        try:
            audio = await eng.fx(
                raw,
                name,
                effects=effects,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio, output_format, output_url)

    # ── MIDI tools ──────────────────────────────────────────────────────────

    @mcp.tool()
    async def midi_compose(
        spec: dict[str, Any],
        output_path: str | None = None,
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Compose MIDI bytes from a song spec.

        `spec` is the same JSON shape accepted by /v1/midi/compose:
        ``{tempo_bpm, time_signature, tracks: [{program, channel,
        notes: [{pitch, start_beats, duration_beats, velocity}]}]}``.

        Returns base64 MIDI by default, or writes to staging if
        `output_path` is set, or PUTs to a presigned URL if `output_url`
        is set. The returned dict carries `size` and either
        `midi_base64` / `path` / `url`.
        """
        eng = engines.get("midi-compose")
        if eng is None or not hasattr(eng, "compose"):
            raise ValueError("midi-compose engine not configured")
        try:
            midi = await eng.compose(spec)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

        if output_path:
            try:
                rel = files_mod.sanitize_path(output_path)
                dest = files_mod.resolve_under(config.FILES_DIR, rel)
            except files_mod.FilePathError as exc:
                raise ValueError(str(exc)) from exc
            files_mod.write_atomic(dest, midi)
            return {"path": str(rel), "size": len(midi)}
        if output_url:
            try:
                await fetch.upload_bytes(output_url, midi, "audio/midi")
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {"url": output_url, "size": len(midi)}
        return {
            "midi_base64": base64.b64encode(midi).decode("ascii"),
            "size": len(midi),
        }

    @mcp.tool()
    async def midi_render(
        file_path: str | None = None,
        file_url: str | None = None,
        soundfont_path: str | None = None,
        output_format: str = "wav",
        gain: float = 0.5,
        samplerate: int = 44100,
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Render a MIDI file to audio via fluidsynth + SoundFont.

        Provide exactly one of `file_path` (staged MIDI) or `file_url`
        (remote MIDI — subject to fetch policy). `soundfont_path`
        optionally overrides the server's default SoundFont with a
        staged ``.sf2``. Returns base64 audio unless `output_url` is set.
        """
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("midi-render")
        if eng is None or not hasattr(eng, "render"):
            raise ValueError("midi-render engine not configured")
        try:
            audio = await eng.render(
                raw,
                name,
                soundfont_path=soundfont_path,
                output_format=output_format,
                gain=gain,
                samplerate=samplerate,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio, output_format, output_url)

    @mcp.tool()
    async def midi_generate(
        spec: dict[str, Any],
        soundfont_path: str | None = None,
        output_format: str = "wav",
        gain: float = 0.5,
        samplerate: int = 44100,
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Compose AND render a song spec in one call — JSON in, audio
        out. Convenience wrapper around midi_compose + midi_render."""
        compose_eng = engines.get("midi-compose")
        render_eng = engines.get("midi-render")
        if compose_eng is None or render_eng is None:
            raise ValueError("midi-compose and midi-render must both be configured")
        try:
            midi = await compose_eng.compose(spec)
            audio = await render_eng.render(
                midi,
                "composed.mid",
                soundfont_path=soundfont_path,
                output_format=output_format,
                gain=gain,
                samplerate=samplerate,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        result = await _emit_audio(audio, output_format, output_url)
        result["midi_size"] = len(midi)
        return result

    # ── MIR analysis tools (librosa) ────────────────────────────────────────

    @mcp.tool()
    async def beats(
        file_path: str | None = None,
        file_url: str | None = None,
        click_track: bool = False,
        output_format: str = "wav",
    ) -> dict[str, Any]:
        """Beat tracking. Returns tempo + beat positions in seconds.
        With ``click_track=True`` also returns base64 audio of input
        mixed with a metronome click on each beat."""
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("librosa-analyze")
        if eng is None or not hasattr(eng, "beats"):
            raise ValueError("librosa-analyze engine not configured")
        try:
            return await eng.beats(
                raw,
                name,
                click_track=click_track,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool()
    async def onsets(
        file_path: str | None = None,
        file_url: str | None = None,
    ) -> dict[str, Any]:
        """Onset (transient) detection. Returns time + relative strength
        for each detected attack."""
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("librosa-analyze")
        if eng is None or not hasattr(eng, "onsets"):
            raise ValueError("librosa-analyze engine not configured")
        try:
            return await eng.onsets(raw, name)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool()
    async def melody(
        file_path: str | None = None,
        file_url: str | None = None,
        fmin: float = 65.0,
        fmax: float = 2093.0,
        as_midi: bool = False,
    ) -> dict[str, Any]:
        """Monophonic pitch tracking via pyin. Returns the pitch contour
        and (with ``as_midi=True``) a base64 MIDI file of quantised
        notes."""
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("librosa-analyze")
        if eng is None or not hasattr(eng, "melody"):
            raise ValueError("librosa-analyze engine not configured")
        try:
            return await eng.melody(
                raw,
                name,
                fmin=fmin,
                fmax=fmax,
                as_midi=as_midi,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool()
    async def segments(
        file_path: str | None = None,
        file_url: str | None = None,
        num_segments: int = 6,
    ) -> dict[str, Any]:
        """Music structure segmentation via recurrence-matrix clustering.
        Returns N labelled ranges; structurally similar regions share a
        label so verse/chorus repetition is easy to spot."""
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("librosa-analyze")
        if eng is None or not hasattr(eng, "segments"):
            raise ValueError("librosa-analyze engine not configured")
        try:
            return await eng.segments(raw, name, num_segments=num_segments)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    # ── silence detection (ffmpeg) ──────────────────────────────────────────

    @mcp.tool()
    async def silence(
        file_path: str | None = None,
        file_url: str | None = None,
        threshold_db: float = -30.0,
        min_duration_sec: float = 0.5,
        trim_mode: str | None = None,
        output_format: str = "wav",
    ) -> dict[str, Any]:
        """Find silent ranges + optionally auto-trim. ``trim_mode='edges'``
        removes leading/trailing silence; ``'all'`` removes every detected
        silence. Output is base64 audio under ``trimmed_audio_base64``."""
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("silence-detect")
        if eng is None or not hasattr(eng, "detect"):
            raise ValueError("silence-detect engine not configured")
        try:
            return await eng.detect(
                raw,
                name,
                threshold_db=threshold_db,
                min_duration_sec=min_duration_sec,
                trim_mode=trim_mode,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    # ── visualisations (ffmpeg) ─────────────────────────────────────────────

    @mcp.tool()
    async def spectrogram(
        file_path: str | None = None,
        file_url: str | None = None,
        width: int = 1920,
        height: int = 1080,
        color: str = "intensity",
        scale: str = "log",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Render a static PNG spectrogram. Returns base64 PNG by default,
        or PUTs to ``output_url`` if set."""
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("ffmpeg-render")
        if eng is None or not hasattr(eng, "spectrogram"):
            raise ValueError("ffmpeg-render engine not configured")
        try:
            png = await eng.spectrogram(
                raw,
                name,
                width=width,
                height=height,
                color=color,
                scale=scale,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        if output_url:
            try:
                await fetch.upload_bytes(output_url, png, "image/png")
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {"url": output_url, "size": len(png), "kind": "spectrogram"}
        return {
            "image_base64": base64.b64encode(png).decode("ascii"),
            "size": len(png),
            "kind": "spectrogram",
        }

    @mcp.tool()
    async def waveform(
        file_path: str | None = None,
        file_url: str | None = None,
        width: int = 1920,
        height: int = 320,
        color: str = "lime",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Render a static PNG waveform. Returns base64 PNG by default."""
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("ffmpeg-render")
        if eng is None or not hasattr(eng, "waveform"):
            raise ValueError("ffmpeg-render engine not configured")
        try:
            png = await eng.waveform(
                raw,
                name,
                width=width,
                height=height,
                color=color,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        if output_url:
            try:
                await fetch.upload_bytes(output_url, png, "image/png")
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {"url": output_url, "size": len(png), "kind": "waveform"}
        return {
            "image_base64": base64.b64encode(png).decode("ascii"),
            "size": len(png),
            "kind": "waveform",
        }

    @mcp.tool()
    async def visualize(
        file_path: str | None = None,
        file_url: str | None = None,
        mode: str = "spectrum",
        width: int = 1280,
        height: int = 720,
        fps: int = 30,
        container: str = "mp4",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Render an animated audio-reactive video. ``mode`` selects the
        ffmpeg filter: spectrum / waves / cqt / freqs / volume /
        vectorscope / phasemeter / histogram. Returns base64 video by
        default, or PUTs to ``output_url`` if set."""
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("ffmpeg-render")
        if eng is None or not hasattr(eng, "visualize"):
            raise ValueError("ffmpeg-render engine not configured")
        try:
            video = await eng.visualize(
                raw,
                name,
                mode=mode,
                width=width,
                height=height,
                fps=fps,
                container=container,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        media_type = "video/mp4" if container == "mp4" else "video/webm"
        if output_url:
            try:
                await fetch.upload_bytes(output_url, video, media_type)
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {
                "url": output_url,
                "size": len(video),
                "mode": mode,
                "container": container,
            }
        return {
            "video_base64": base64.b64encode(video).decode("ascii"),
            "size": len(video),
            "mode": mode,
            "container": container,
        }

    # ── fingerprint (Chromaprint) ──────────────────────────────────────────

    @mcp.tool()
    async def fingerprint(
        file_path: str | None = None,
        file_url: str | None = None,
        analyze_seconds: float = 120.0,
        return_raw: bool = False,
    ) -> dict[str, Any]:
        """Chromaprint audio fingerprint via fpcalc. Returns
        ``{duration, fingerprint}`` (+ ``fingerprint_raw`` int array if
        ``return_raw=True``)."""
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("audio-fingerprint")
        if eng is None or not hasattr(eng, "compute"):
            raise ValueError("audio-fingerprint engine not configured")
        try:
            return await eng.compute(
                raw,
                name,
                analyze_seconds=analyze_seconds,
                return_raw=return_raw,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    # ── UVR audio restoration tools ────────────────────────────────────────

    @mcp.tool()
    async def dereverb(
        file_path: str | None = None,
        file_url: str | None = None,
        engine: str = "uvr-dereverb",
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Remove room reverb from audio using UVR BS-Roformer model.

        Input: file_path (staged file) or file_url (remote URL).
        Returns {audio_base64, size, engine, output_format} or
        {url, size, engine, output_format} if output_url is set.
        engine options: uvr-dereverb (default).
        """
        from .engines import is_uvr_restore_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get(engine)
        if eng is None:
            raise ValueError(f"unknown engine {engine!r}")
        if not is_uvr_restore_engine(eng):
            raise ValueError(f"engine {engine!r} does not support restore operations")
        try:
            audio_bytes = await eng.restore(raw, name, output_format=output_format)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        if output_url:
            try:
                await fetch.upload_bytes(
                    output_url,
                    audio_bytes,
                    content_type_for(output_format),
                )
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {
                "url": output_url,
                "size": len(audio_bytes),
                "engine": engine,
                "output_format": output_format,
            }
        return {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "size": len(audio_bytes),
            "engine": engine,
            "output_format": output_format,
        }

    @mcp.tool()
    async def deecho(
        file_path: str | None = None,
        file_url: str | None = None,
        engine: str = "uvr-deecho",
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Remove echo from audio using UVR VR Architecture model.

        engine options: uvr-deecho (default, normal),
        uvr-deecho-aggressive.
        """
        from .engines import is_uvr_restore_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get(engine)
        if eng is None:
            raise ValueError(f"unknown engine {engine!r}")
        if not is_uvr_restore_engine(eng):
            raise ValueError(f"engine {engine!r} does not support restore operations")
        try:
            audio_bytes = await eng.restore(raw, name, output_format=output_format)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        if output_url:
            try:
                await fetch.upload_bytes(
                    output_url,
                    audio_bytes,
                    content_type_for(output_format),
                )
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {
                "url": output_url,
                "size": len(audio_bytes),
                "engine": engine,
                "output_format": output_format,
            }
        return {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "size": len(audio_bytes),
            "engine": engine,
            "output_format": output_format,
        }

    @mcp.tool()
    async def denoise(
        file_path: str | None = None,
        file_url: str | None = None,
        engine: str = "uvr-denoise",
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Remove broadband background noise using UVR MelBand Roformer (SDR 28).

        engine options: uvr-denoise (default).
        """
        from .engines import is_uvr_restore_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get(engine)
        if eng is None:
            raise ValueError(f"unknown engine {engine!r}")
        if not is_uvr_restore_engine(eng):
            raise ValueError(f"engine {engine!r} does not support restore operations")
        try:
            audio_bytes = await eng.restore(raw, name, output_format=output_format)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        if output_url:
            try:
                await fetch.upload_bytes(
                    output_url,
                    audio_bytes,
                    content_type_for(output_format),
                )
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {
                "url": output_url,
                "size": len(audio_bytes),
                "engine": engine,
                "output_format": output_format,
            }
        return {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "size": len(audio_bytes),
            "engine": engine,
            "output_format": output_format,
        }

    # ── MIDI inspect + transform (mido) ────────────────────────────────────

    @mcp.tool()
    async def midi_inspect(
        file_path: str | None = None,
        file_url: str | None = None,
    ) -> dict[str, Any]:
        """Parse a Standard MIDI File and return JSON describing tempo,
        time signature, key signature, and per-track stats. Counterpart
        to midi_compose."""
        raw, _name = await _load_input(file_path, file_url)
        eng = engines.get("midi-compose")
        if eng is None or not hasattr(eng, "inspect"):
            raise ValueError("midi-compose engine not configured")
        try:
            return await eng.inspect(raw)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool()
    async def midi_transform(
        file_path: str | None = None,
        file_url: str | None = None,
        transpose_semitones: int = 0,
        quantize_grid_beats: float | None = None,
        tempo_bpm: float | None = None,
        keep_channels: list[int] | None = None,
        drop_channels: list[int] | None = None,
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Transform a MIDI file: transpose / quantize / change tempo /
        filter channels. Returns base64 MIDI by default."""
        raw, _name = await _load_input(file_path, file_url)
        eng = engines.get("midi-compose")
        if eng is None or not hasattr(eng, "transform"):
            raise ValueError("midi-compose engine not configured")
        try:
            out = await eng.transform(
                raw,
                transpose_semitones=transpose_semitones,
                quantize_grid_beats=quantize_grid_beats,
                tempo_bpm=tempo_bpm,
                keep_channels=keep_channels,
                drop_channels=drop_channels,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        if output_url:
            try:
                await fetch.upload_bytes(output_url, out, "audio/midi")
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {"url": output_url, "size": len(out)}
        return {
            "midi_base64": base64.b64encode(out).decode("ascii"),
            "size": len(out),
        }

    # ── audio-to-MIDI (basic-pitch) ────────────────────────────────────────

    @mcp.tool()
    async def audio_to_midi(
        file_path: str | None = None,
        file_url: str | None = None,
        engine: str = "basic-pitch",
        onset_threshold: float = 0.5,
        frame_threshold: float = 0.3,
        minimum_note_length_ms: float = 58.0,
        minimum_frequency: float | None = None,
        maximum_frequency: float | None = None,
        multiple_pitch_bends: bool = False,
        melodia_trick: bool = True,
        output_path: str | None = None,
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Convert audio to a polyphonic MIDI file via Spotify basic-pitch.

        Provide exactly one of `file_path` or `file_url`. Returns
        `{midi_base64, size, engine}` by default, or writes to staging
        if `output_path` is set, or PUTs to a presigned URL if
        `output_url` is set.
        """
        from .engines import is_basic_pitch_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get(engine)
        if eng is None:
            raise ValueError(f"unknown engine {engine!r}")
        if not is_basic_pitch_engine(eng):
            raise ValueError(
                f"engine {engine!r} does not support audio-to-MIDI transcription"
            )
        try:
            midi = await eng.to_midi(
                raw,
                name,
                onset_threshold=onset_threshold,
                frame_threshold=frame_threshold,
                minimum_note_length_ms=minimum_note_length_ms,
                minimum_frequency=minimum_frequency,
                maximum_frequency=maximum_frequency,
                multiple_pitch_bends=multiple_pitch_bends,
                melodia_trick=melodia_trick,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

        if output_path:
            try:
                rel = files_mod.sanitize_path(output_path)
                dest = files_mod.resolve_under(config.FILES_DIR, rel)
            except files_mod.FilePathError as exc:
                raise ValueError(str(exc)) from exc
            files_mod.write_atomic(dest, midi)
            return {"path": str(rel), "size": len(midi), "engine": engine}
        if output_url:
            try:
                await fetch.upload_bytes(output_url, midi, "audio/midi")
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {"url": output_url, "size": len(midi), "engine": engine}
        return {
            "midi_base64": base64.b64encode(midi).decode("ascii"),
            "size": len(midi),
            "engine": engine,
        }

    # ── neural enhancement (DeepFilterNet) ────────────────────────────────

    @mcp.tool()
    async def enhance(
        file_path: str | None = None,
        file_url: str | None = None,
        engine: str = "deepfilter",
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Neural speech and vocal enhancement via DeepFilterNet DF3.

        Provide exactly one of `file_path` or `file_url`. Returns
        `{audio_base64, size, engine, output_format}` by default,
        or `{url, size, engine, output_format}` if `output_url` is set.
        """
        from .engines import is_deepfilter_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get(engine)
        if eng is None:
            raise ValueError(f"unknown engine {engine!r}")
        if not is_deepfilter_engine(eng):
            raise ValueError(
                f"engine {engine!r} does not support neural enhancement"
            )
        try:
            audio_bytes = await eng.enhance(raw, name, output_format=output_format)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        if output_url:
            try:
                await fetch.upload_bytes(
                    output_url,
                    audio_bytes,
                    content_type_for(output_format),
                )
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {
                "url": output_url,
                "size": len(audio_bytes),
                "engine": engine,
                "output_format": output_format,
            }
        return {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "size": len(audio_bytes),
            "engine": engine,
            "output_format": output_format,
        }

    # ── chord + key detection (librosa) ───────────────────────────────────────

    @mcp.tool()
    async def chords(
        file_path: str | None = None,
        file_url: str | None = None,
        hop_length: int = 512,
        segment_min_duration_sec: float = 0.5,
    ) -> dict[str, Any]:
        """Chord + key detection via librosa chroma analysis.
        Returns detected key with confidence, and time-stamped chord segments."""
        from .engines import is_chord_detect_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("chord-detect")
        if eng is None:
            raise ValueError("chord-detect engine not configured")
        if not is_chord_detect_engine(eng):
            raise ValueError("chord-detect engine does not support chord detection")
        try:
            return await eng.detect_chords(
                raw,
                name,
                hop_length=hop_length,
                segment_min_duration_sec=segment_min_duration_sec,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool()
    async def vad(
        file_path: str | None = None,
        file_url: str | None = None,
        threshold: float = 0.5,
        min_speech_duration_ms: float = 250.0,
        min_silence_duration_ms: float = 100.0,
    ) -> dict[str, Any]:
        """Voice activity detection via silero-vad. Returns speech/non-speech segments
        with timestamps and overall speech ratio."""
        from .engines import is_vad_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("silero-vad")
        if eng is None:
            raise ValueError("silero-vad engine not configured")
        if not is_vad_engine(eng):
            raise ValueError("silero-vad engine does not support voice activity detection")
        try:
            return await eng.detect_voice(
                raw,
                name,
                threshold=threshold,
                min_speech_duration_ms=min_speech_duration_ms,
                min_silence_duration_ms=min_silence_duration_ms,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool()
    async def diarize(
        file_path: str | None = None,
        file_url: str | None = None,
        engine: str = "pyannote",
        num_speakers: int | None = None,
        min_speakers: int | None = None,
        max_speakers: int | None = None,
    ) -> dict[str, Any]:
        """Speaker diarization — who spoke when. Returns time-stamped speaker segments.
        engine options: pyannote (default, requires HUGGINGFACE_TOKEN)."""
        from .engines import is_diarize_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get(engine)
        if eng is None:
            raise ValueError(f"unknown engine {engine!r}")
        if not is_diarize_engine(eng):
            raise ValueError(f"engine {engine!r} does not support speaker diarization")
        try:
            return await eng.diarize(
                raw,
                name,
                num_speakers=num_speakers,
                min_speakers=min_speakers,
                max_speakers=max_speakers,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    # ── stretch / tag / embed ───────────────────────────────────────────────

    @mcp.tool()
    async def stretch(
        file_path: str | None = None,
        file_url: str | None = None,
        output_path: str | None = None,
        tempo_factor: float = 1.0,
        pitch_semitones: float = 0.0,
        output_format: str = "wav",
    ) -> dict[str, Any]:
        """Time-stretch and/or pitch-shift audio. tempo_factor=0.5 halves speed;
        pitch_semitones=12 shifts one octave up. Returns base64 audio (or writes
        to output_path in staging)."""
        from .engines import is_stretch_engine  # noqa: PLC0415
        from .audio import content_type_for  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("stretch")
        if eng is None or not is_stretch_engine(eng):
            raise ValueError("stretch engine not configured")
        try:
            audio_bytes = await eng.stretch(
                raw, name,
                tempo_factor=tempo_factor,
                pitch_semitones=pitch_semitones,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        if output_path:
            try:
                rel = files_mod.sanitize_path(output_path)
                dest = files_mod.resolve_under(config.FILES_DIR, rel)
            except files_mod.FilePathError as exc:
                raise ValueError(str(exc)) from exc
            files_mod.write_atomic(dest, audio_bytes)
            return {"path": str(rel), "size": len(audio_bytes)}
        return {
            "audio_base64": base64.b64encode(audio_bytes).decode("ascii"),
            "content_type": content_type_for(output_format),
            "size": len(audio_bytes),
        }

    @mcp.tool()
    async def tag(
        file_path: str | None = None,
        file_url: str | None = None,
        top_k: int = 10,
    ) -> dict[str, Any]:
        """Audio tagging via Audio Spectrogram Transformer — returns top-K
        AudioSet class labels with confidence scores. Requires HF model cache."""
        from .engines import is_tag_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("ast-tag")
        if eng is None or not is_tag_engine(eng):
            raise ValueError("ast-tag engine not configured")
        try:
            return await eng.tag(raw, name, top_k=top_k)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool()
    async def embed(
        file_path: str | None = None,
        file_url: str | None = None,
        query_text: str | None = None,
    ) -> dict[str, Any]:
        """512-dim L2-normalised audio embedding via LAION CLAP. With query_text,
        also returns cosine similarity to the text description.
        Requires HF model cache."""
        from .engines import is_embed_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("clap-embed")
        if eng is None or not is_embed_engine(eng):
            raise ValueError("clap-embed engine not configured")
        try:
            return await eng.embed(raw, name, query_text=query_text)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    # ── audio utilities (info / trim / mix / classify) ─────────────────────

    @mcp.tool()
    async def info(
        file_path: str | None = None,
        file_url: str | None = None,
    ) -> dict[str, Any]:
        """Probe audio file metadata — duration, sample_rate, channels, codec,
        bit_depth, format, size_bytes. No engine required; works on any format."""
        from .audio import audio_info as _audio_info  # noqa: PLC0415
        import asyncio as _asyncio  # noqa: PLC0415
        raw, name = await _load_input(file_path, file_url)
        try:
            return await _asyncio.to_thread(_audio_info, raw, name)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool()
    async def trim(
        file_path: str | None = None,
        file_url: str | None = None,
        start_sec: float = 0.0,
        end_sec: float = 0.0,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Cut audio to [start_sec, end_sec). end_sec required and must be > start_sec.
        Returns base64 audio unless output_url is set (presigned PUT)."""
        from .audio import trim_audio as _trim  # noqa: PLC0415
        import asyncio as _asyncio  # noqa: PLC0415
        if end_sec <= start_sec:
            raise ValueError("end_sec must be > start_sec")
        raw, name = await _load_input(file_path, file_url)
        try:
            audio_bytes = await _asyncio.to_thread(
                _trim, raw, name, start_sec, end_sec, output_format
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    @mcp.tool()
    async def mix(
        tracks: list[dict[str, Any]],
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Mix multiple audio tracks with per-track gain.
        tracks: list of {file_path or file_url, gain_db (optional, default 0.0)}.
        Requires at least 2 tracks. Returns base64 audio unless output_url is set."""
        from .audio import mix_audio as _mix  # noqa: PLC0415
        import asyncio as _asyncio  # noqa: PLC0415
        if len(tracks) < 2:
            raise ValueError("mix requires at least 2 tracks")
        mix_inputs: list[tuple[bytes, str, float]] = []
        for i, spec in enumerate(tracks):
            fp = spec.get("file_path") or None
            fu = spec.get("file_url") or None
            gain_db = float(spec.get("gain_db", 0.0))
            try:
                raw, name = await _load_input(fp, fu)
            except ValueError as exc:
                raise ValueError(f"track {i}: {exc}") from exc
            mix_inputs.append((raw, name, gain_db))
        try:
            audio_bytes = await _asyncio.to_thread(_mix, mix_inputs, output_format)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    @mcp.tool()
    async def classify(
        file_path: str | None = None,
        file_url: str | None = None,
        labels: list[str] = [],
    ) -> dict[str, Any]:
        """Zero-shot audio classification via CLAP. Provide a list of labels
        (genres, moods, instruments — any free-form text). Returns results sorted
        by descending similarity score. Requires clap-embed model cache."""
        if not labels:
            raise ValueError("labels must be a non-empty list of strings")
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("clap-embed")
        if eng is None or not hasattr(eng, "classify"):
            raise ValueError("clap-embed engine not configured")
        try:
            return await eng.classify(raw, name, labels=labels)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool()
    async def fade(
        file_path: str | None = None,
        file_url: str | None = None,
        fade_in: float = 0.0,
        fade_out: float = 0.0,
        curve: str = "tri",
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Apply fade-in/fade-out. curve: tri/qsin/esin/hsin/log/exp/lin/etc.
        At least one of fade_in/fade_out must be > 0. Returns base64 audio."""
        from .audio import fade_audio as _fade  # noqa: PLC0415
        import asyncio as _asyncio  # noqa: PLC0415
        if fade_in <= 0.0 and fade_out <= 0.0:
            raise ValueError("at least one of fade_in or fade_out must be > 0")
        raw, name = await _load_input(file_path, file_url)
        try:
            audio_bytes = await _asyncio.to_thread(
                _fade, raw, name, output_format,
                fade_in=fade_in, fade_out=fade_out, curve=curve,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    @mcp.tool()
    async def reverse(
        file_path: str | None = None,
        file_url: str | None = None,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Reverse audio playback direction. Returns base64 audio."""
        from .audio import reverse_audio as _reverse  # noqa: PLC0415
        import asyncio as _asyncio  # noqa: PLC0415
        raw, name = await _load_input(file_path, file_url)
        try:
            audio_bytes = await _asyncio.to_thread(_reverse, raw, name, output_format)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    @mcp.tool()
    async def loop(
        file_path: str | None = None,
        file_url: str | None = None,
        count: int = 2,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Repeat audio count times (minimum 2). Returns base64 audio."""
        from .audio import loop_audio as _loop  # noqa: PLC0415
        import asyncio as _asyncio  # noqa: PLC0415
        if count < 2:
            raise ValueError(f"count must be >= 2, got {count}")
        raw, name = await _load_input(file_path, file_url)
        try:
            audio_bytes = await _asyncio.to_thread(_loop, raw, name, output_format, count)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    @mcp.tool()
    async def bpm_match(
        file_path: str | None = None,
        file_url: str | None = None,
        target_bpm: float = 120.0,
        pitch_semitones: float = 0.0,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Detect source BPM then time-stretch to target_bpm.
        Requires librosa-analyze + stretch engines.
        Returns base64 audio + {source_bpm, target_bpm, tempo_factor}."""
        from .engines import is_beats_engine as _is_beats  # noqa: PLC0415
        from .engines import is_stretch_engine as _is_stretch  # noqa: PLC0415
        if target_bpm <= 0:
            raise ValueError(f"target_bpm must be > 0, got {target_bpm}")
        librosa_eng = engines.get("librosa-analyze")
        if librosa_eng is None or not _is_beats(librosa_eng):
            raise ValueError("librosa-analyze engine not configured")
        stretch_eng = engines.get("stretch")
        if stretch_eng is None or not _is_stretch(stretch_eng):
            raise ValueError("stretch engine not configured")
        raw, name = await _load_input(file_path, file_url)
        try:
            beats_result = await librosa_eng.beats(raw, name)
            source_bpm = beats_result["tempo"]
            tempo_factor = target_bpm / source_bpm
            audio_bytes = await stretch_eng.stretch(
                raw,
                name,
                tempo_factor=tempo_factor,
                pitch_semitones=pitch_semitones,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        result = await _emit_audio(audio_bytes, output_format, output_url)
        result["source_bpm"] = round(source_bpm, 2)
        result["target_bpm"] = target_bpm
        result["tempo_factor"] = round(tempo_factor, 4)
        return result

    @mcp.tool()
    async def stereo_width(
        file_path: str | None = None,
        file_url: str | None = None,
        width: float = 1.0,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Adjust stereo image width via M/S processing.
        width=0.0 → mono, 1.0 → original, >1.0 → wider. Range: [0.0, 3.0].
        Returns base64 audio."""
        from .audio import stereo_width_audio as _stereo_width  # noqa: PLC0415
        import asyncio as _asyncio  # noqa: PLC0415
        if not (0.0 <= width <= 3.0):
            raise ValueError(f"width must be in [0.0, 3.0], got {width}")
        raw, name = await _load_input(file_path, file_url)
        try:
            audio_bytes = await _asyncio.to_thread(
                _stereo_width, raw, name, output_format, width
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    # ── split / pan / eq / key-match / sidechain-duck ─────────────────────────

    @mcp.tool()
    async def split(
        file_path: str | None = None,
        file_url: str | None = None,
        mode: str = "equal",
        count: int | None = None,
        threshold_db: float = -30.0,
        min_duration_sec: float = 0.5,
        output_format: str = "wav",
    ) -> dict[str, Any]:
        """Split audio into segments.
        mode=equal: requires count>=2, splits into equal time parts.
        mode=silence: splits on quiet gaps (uses threshold_db/min_duration_sec).
        Returns {segments: [{name, audio_base64}, ...]}."""
        import asyncio as _asyncio  # noqa: PLC0415
        from .audio import (  # noqa: PLC0415
            split_audio_equal as _split_equal,
            trim_audio as _trim,
        )
        from .engines import is_silence_engine as _is_silence  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        if mode == "equal":
            if count is None or count < 2:
                raise ValueError("mode=equal requires count >= 2")
            try:
                segs = await _asyncio.to_thread(
                    _split_equal, raw, name, output_format, count
                )
            except AudioConversionError as exc:
                raise ValueError(str(exc)) from exc
        elif mode == "silence":
            eng = engines.get("silence-detect")
            if eng is None or not _is_silence(eng):
                raise ValueError("silence-detect engine not configured")
            try:
                result = await eng.detect(
                    raw, name,
                    threshold_db=threshold_db,
                    min_duration_sec=min_duration_sec,
                )
            except AudioConversionError as exc:
                raise ValueError(str(exc)) from exc
            non_silent_ranges = result.get("non_silent_ranges", [])
            if not non_silent_ranges:
                raise ValueError("no non-silent segments found")
            segs = []
            for r in non_silent_ranges:
                try:
                    seg = await _asyncio.to_thread(
                        _trim, raw, name,
                        r["start_sec"], r["end_sec"], output_format,
                    )
                except AudioConversionError as exc:
                    raise ValueError(str(exc)) from exc
                segs.append(seg)
        else:
            raise ValueError("mode must be 'equal' or 'silence'")
        return {
            "segments": [
                {
                    "name": f"segment_{i:03d}.{output_format}",
                    "audio_base64": base64.b64encode(seg).decode(),
                }
                for i, seg in enumerate(segs)
            ],
            "count": len(segs),
        }

    @mcp.tool()
    async def pan(
        file_path: str | None = None,
        file_url: str | None = None,
        position: float = 0.0,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Pan audio in the stereo field.
        position: -1.0=hard left, 0.0=center, 1.0=hard right.
        Returns base64 audio."""
        import asyncio as _asyncio  # noqa: PLC0415
        from .audio import pan_audio as _pan  # noqa: PLC0415

        if not (-1.0 <= position <= 1.0):
            raise ValueError(f"position must be in [-1.0, 1.0], got {position}")
        raw, name = await _load_input(file_path, file_url)
        try:
            audio_bytes = await _asyncio.to_thread(
                _pan, raw, name, output_format, position
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    @mcp.tool()
    async def eq(
        file_path: str | None = None,
        file_url: str | None = None,
        bands: list[dict[str, Any]] = [],
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Parametric EQ. bands: [{freq, gain_db, width_hz (opt)}].
        Returns base64 audio."""
        import asyncio as _asyncio  # noqa: PLC0415
        from .audio import eq_audio as _eq  # noqa: PLC0415

        if not bands:
            raise ValueError("bands must contain at least one entry")
        raw, name = await _load_input(file_path, file_url)
        try:
            audio_bytes = await _asyncio.to_thread(
                _eq, raw, name, output_format, bands
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    @mcp.tool()
    async def key_match(
        file_path: str | None = None,
        file_url: str | None = None,
        target_key: str = "C",
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Detect source key then pitch-shift to target_key (e.g. C, F#, Bb).
        Returns base64 audio + {source_key, target_key, semitones}.
        Requires chord-detect + stretch engines."""
        from .engines import (  # noqa: PLC0415
            is_chord_detect_engine as _is_chord,
            is_stretch_engine as _is_stretch,
        )

        _NOTE_MAP: dict[str, int] = {
            "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3,
            "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8,
            "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11,
        }
        _MODE_SFX = frozenset({"MAJOR", "MINOR", "MAJ", "MIN", "M"})

        def _parse_root(key_str: str) -> int:
            parts = key_str.strip().upper().split()
            root = parts[0]
            for sfx in sorted(_MODE_SFX, key=len, reverse=True):
                if root.endswith(sfx) and len(root) > len(sfx):
                    root = root[: -len(sfx)]
                    break
            val = _NOTE_MAP.get(root)
            if val is None:
                raise ValueError(
                    f"unrecognised key root {root!r}; "
                    f"valid roots: {list(_NOTE_MAP.keys())}"
                )
            return val

        target_semitone = _parse_root(target_key)
        chord_eng = engines.get("chord-detect")
        if chord_eng is None or not _is_chord(chord_eng):
            raise ValueError("chord-detect engine not configured")
        stretch_eng = engines.get("stretch")
        if stretch_eng is None or not _is_stretch(stretch_eng):
            raise ValueError("stretch engine not configured")
        raw, name = await _load_input(file_path, file_url)
        try:
            source_result = await chord_eng.detect_chords(raw, name)
            source_key = source_result["key"]
            source_semitone = _parse_root(source_key)
            diff = (target_semitone - source_semitone) % 12
            if diff > 6:
                diff -= 12
            audio_bytes = await stretch_eng.stretch(
                raw, name,
                tempo_factor=1.0,
                pitch_semitones=float(diff),
                output_format=output_format,
            )
        except (AudioConversionError, ValueError):
            raise
        except Exception as exc:
            raise ValueError(str(exc)) from exc
        result = await _emit_audio(audio_bytes, output_format, output_url)
        result["source_key"] = source_key
        result["target_key"] = target_key.strip()
        result["semitones"] = diff
        return result

    @mcp.tool()
    async def sidechain_duck(
        file_path: str | None = None,
        file_url: str | None = None,
        trigger_file_path: str | None = None,
        trigger_file_url: str | None = None,
        threshold_db: float = -20.0,
        ratio: float = 4.0,
        attack_ms: float = 10.0,
        release_ms: float = 200.0,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Duck primary audio when trigger audio is loud.
        Provide primary via file_path/file_url, trigger via
        trigger_file_path/trigger_file_url.
        Returns base64 audio."""
        import asyncio as _asyncio  # noqa: PLC0415
        from .audio import sidechain_duck as _duck  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        trigger_raw, trigger_name = await _load_input(
            trigger_file_path, trigger_file_url, field_prefix="trigger_file"
        )
        try:
            audio_bytes = await _asyncio.to_thread(
                _duck,
                raw, name,
                trigger_raw, trigger_name,
                output_format,
                threshold_db, ratio, attack_ms, release_ms,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    # ── audio utilities: concat / speed / convert / similar / midi_quantize ──

    @mcp.tool()
    async def concat(
        files: list[dict[str, Any]],
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Concatenate N audio files in order.
        files: list of {file_path or file_url}. Requires at least 2.
        Returns base64 audio unless output_url is set."""
        from .audio import concat_audio as _concat  # noqa: PLC0415
        import asyncio as _asyncio  # noqa: PLC0415
        if len(files) < 2:
            raise ValueError("concat requires at least 2 files")
        concat_inputs: list[tuple[bytes, str]] = []
        for i, spec in enumerate(files):
            fp = spec.get("file_path") or None
            fu = spec.get("file_url") or None
            try:
                raw, name = await _load_input(fp, fu)
            except ValueError as exc:
                raise ValueError(f"file {i}: {exc}") from exc
            concat_inputs.append((raw, name))
        try:
            audio_bytes = await _asyncio.to_thread(_concat, concat_inputs, output_format)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    @mcp.tool()
    async def speed(
        file_path: str | None = None,
        file_url: str | None = None,
        speed: float = 1.0,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Change playback speed without pitch shift via ffmpeg atempo.
        speed=0.5 halves speed; speed=2.0 doubles. Range: 0.1–10.0.
        Returns base64 audio unless output_url is set."""
        from .audio import speed_audio as _speed  # noqa: PLC0415
        import asyncio as _asyncio  # noqa: PLC0415
        if not (0.1 <= speed <= 10.0):
            raise ValueError(f"speed must be in [0.1, 10.0], got {speed}")
        raw, name = await _load_input(file_path, file_url)
        try:
            audio_bytes = await _asyncio.to_thread(_speed, raw, name, speed, output_format)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    @mcp.tool()
    async def convert(
        file_path: str | None = None,
        file_url: str | None = None,
        output_format: str = "wav",
        sample_rate: int | None = None,
        channels: int | None = None,
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Re-encode audio to a different format, sample rate, or channel count.
        output_format: wav/mp3/flac/opus/aac/pcm. sample_rate: e.g. 16000, 44100, 48000.
        channels: 1 (mono) or 2 (stereo). Returns base64 audio unless output_url is set."""
        from .audio import convert_audio as _convert  # noqa: PLC0415
        import asyncio as _asyncio  # noqa: PLC0415
        raw, name = await _load_input(file_path, file_url)
        try:
            audio_bytes = await _asyncio.to_thread(
                _convert, raw, name, output_format, sample_rate, channels
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    @mcp.tool()
    async def similar(
        file_path: str | None = None,
        file_url: str | None = None,
        reference_file_path: str | None = None,
        reference_file_url: str | None = None,
    ) -> dict[str, Any]:
        """Cosine similarity between two audio files via CLAP embeddings.
        Returns {similarity: float [-1,1], dim: 512}. Requires clap-embed model cache."""
        from .engines import is_embed_engine  # noqa: PLC0415
        raw_a, name_a = await _load_input(file_path, file_url)
        raw_b, name_b = await _load_input(
            reference_file_path, reference_file_url, field_prefix="reference_file"
        )
        eng = engines.get("clap-embed")
        if eng is None or not is_embed_engine(eng):
            raise ValueError("clap-embed engine not configured")
        try:
            return await eng.similar(raw_a, name_a, raw_b, name_b)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    @mcp.tool()
    async def midi_quantize(
        file_path: str | None = None,
        file_url: str | None = None,
        grid_beats: float = 0.25,
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Snap MIDI note timings to the nearest rhythmic grid.
        grid_beats: 0.25=16th note, 0.5=8th, 1.0=quarter. Returns base64 MIDI."""
        if grid_beats <= 0:
            raise ValueError(f"grid_beats must be > 0, got {grid_beats}")
        raw, _name = await _load_input(file_path, file_url)
        eng = engines.get("midi-compose")
        if eng is None or not hasattr(eng, "transform"):
            raise ValueError("midi-compose engine not configured")
        try:
            out = await eng.transform(raw, quantize_grid_beats=grid_beats)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        if output_url:
            try:
                await fetch.upload_bytes(output_url, out, "audio/midi")
            except fetch.FetchError as exc:
                raise ValueError(str(exc)) from exc
            return {"url": output_url, "size": len(out), "grid_beats": grid_beats}
        return {
            "midi_base64": base64.b64encode(out).decode("ascii"),
            "size": len(out),
            "grid_beats": grid_beats,
        }

    # ── HPSS + noise reduction ──────────────────────────────────────────────

    @mcp.tool()
    async def hpss(
        file_path: str | None = None,
        file_url: str | None = None,
        margin: float = 1.0,
        kernel_size: int = 31,
        output_format: str = "wav",
    ) -> dict[str, Any]:
        """Harmonic/percussive source separation via librosa HPSS median filter.

        Provide exactly one of `file_path` or `file_url`. Returns
        ``{stems: {harmonic: <base64>, percussive: <base64>}, output_format}``.
        ``margin`` ≥1.0 controls separation aggressiveness; ``kernel_size``
        sets the median filter width (odd int, default 31).
        """
        from .engines import is_hpss_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("hpss")
        if eng is None or not is_hpss_engine(eng):
            raise ValueError("hpss engine not configured")
        try:
            result = await eng.hpss(
                raw,
                name,
                margin=margin,
                kernel_size=kernel_size,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return {
            "stems": {
                stem: base64.b64encode(audio).decode("ascii")
                for stem, audio in result.items()
            },
            "output_format": output_format,
        }

    @mcp.tool()
    async def noise_reduce(
        file_path: str | None = None,
        file_url: str | None = None,
        stationary: bool = False,
        prop_decrease: float = 1.0,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Spectral noise reduction via noisereduce (no GPU required).

        Provide exactly one of `file_path` or `file_url`.
        ``stationary=True`` targets constant noise (hum/hiss);
        ``False`` uses adaptive non-stationary mode (default).
        ``prop_decrease`` in [0,1] scales how aggressively noise is
        removed (1.0 = full). Returns base64 audio unless ``output_url``
        is set (presigned PUT).
        """
        from .engines import is_noise_reduce_engine  # noqa: PLC0415

        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("noise-reduce")
        if eng is None or not is_noise_reduce_engine(eng):
            raise ValueError("noise-reduce engine not configured")
        try:
            audio_bytes = await eng.reduce(
                raw,
                name,
                stationary=stationary,
                prop_decrease=prop_decrease,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio_bytes, output_format, output_url)

    # ── file staging tools ──────────────────────────────────────────────────

    @mcp.tool()
    async def list_files() -> dict[str, Any]:
        """List files in the staging area."""
        return {"files": files_mod.list_files(config.FILES_DIR)}

    @mcp.tool()
    async def put_file(path: str, content_base64: str) -> dict[str, Any]:
        """Upload a file (base64-encoded) to the staging area."""
        try:
            data = base64.b64decode(content_base64, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError(f"content_base64 is not valid base64: {exc}") from exc
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise ValueError(
                f"upload too large ({len(data)} bytes > " f"{config.MAX_UPLOAD_BYTES})"
            )
        try:
            rel = files_mod.sanitize_path(path)
            dest = files_mod.resolve_under(config.FILES_DIR, rel)
        except files_mod.FilePathError as exc:
            raise ValueError(str(exc)) from exc
        files_mod.write_atomic(dest, data)
        return {"path": str(rel), "size": len(data)}

    @mcp.tool()
    async def get_file(path: str) -> dict[str, Any]:
        """Read a staged file (base64-encoded back)."""
        data, rel = _load_staged(path)
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise ValueError(
                f"file too large to return over MCP "
                f"({len(data)} bytes > {config.MAX_UPLOAD_BYTES})"
            )
        return {
            "path": rel,
            "size": len(data),
            "content_base64": base64.b64encode(data).decode("ascii"),
        }

    @mcp.tool()
    async def delete_file(path: str) -> dict[str, Any]:
        """Delete a staged file."""
        try:
            rel = files_mod.sanitize_path(path)
            target = files_mod.resolve_under(config.FILES_DIR, rel)
        except files_mod.FilePathError as exc:
            raise ValueError(str(exc)) from exc
        if target.is_symlink() or not target.is_file():
            raise ValueError(f"file not found: {rel}")
        target.unlink()
        files_mod.prune_empty_parents(target, config.FILES_DIR)
        return {"deleted": str(rel)}

    # ── metadata — read / write audio tags ─────────────────────────────────

    @mcp.tool()
    async def audio_metadata(
        file_path: str | None = None,
        file_url: str | None = None,
        tags: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Read or write audio file tags (ID3 for MP3, Vorbis for FLAC/OGG).
        Without tags: returns title, artist, album, year, bpm, key, etc.
        With tags: writes provided fields and returns updated tag set."""
        from .engines import is_metadata_engine  # noqa: PLC0415
        eng = next((e for e in engines.values() if is_metadata_engine(e)), None)
        if eng is None:
            raise ValueError("metadata engine not configured")
        raw, filename = await _load_input(file_path, file_url)
        try:
            if tags is not None:
                updated_bytes = await eng.write_tags(raw, filename, tags)
                return await eng.read_tags(updated_bytes, filename)
            return await eng.read_tags(raw, filename)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    # ── clip_detect — detect digital clipping ──────────────────────────────

    @mcp.tool()
    async def detect_clipping(
        file_path: str | None = None,
        file_url: str | None = None,
    ) -> dict[str, Any]:
        """Detect digital clipping in an audio file.
        Returns: clipped, clip_count, clip_ratio, peak_db, duration_sec,
        sample_rate, channels."""
        raw, filename = await _load_input(file_path, file_url)
        try:
            return await asyncio.to_thread(clip_detect, raw, filename)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc

    # ── mid_side — M/S encode or decode ────────────────────────────────────

    @mcp.tool()
    async def mid_side(
        file_path: str | None = None,
        file_url: str | None = None,
        mode: str = "encode",
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Encode stereo audio to Mid/Side or decode M/S back to L/R.
        mode: 'encode' (L+R→Mid, L-R→Side) or 'decode' (Mid+Side→L/R).
        Returns audio base64 or uploads to output_url."""
        if mode not in ("encode", "decode"):
            raise ValueError("mode must be 'encode' or 'decode'")
        raw, filename = await _load_input(file_path, file_url)
        try:
            fn = mid_side_encode if mode == "encode" else mid_side_decode
            result = await asyncio.to_thread(fn, raw, filename, output_format)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(result, output_format, output_url)

    # ── beat_slice — slice audio at beat positions ──────────────────────────

    @mcp.tool()
    async def slice_at_beats(
        file_path: str | None = None,
        file_url: str | None = None,
        output_format: str = "wav",
    ) -> dict[str, Any]:
        """Slice audio at beat positions detected by librosa-analyze.
        Returns a base64-encoded ZIP of numbered beat slice WAV/MP3 files."""
        from .engines import is_beats_engine  # noqa: PLC0415
        librosa_eng = engines.get("librosa-analyze")
        if librosa_eng is None or not is_beats_engine(librosa_eng):
            raise ValueError("librosa-analyze engine not configured")
        raw, filename = await _load_input(file_path, file_url)
        try:
            beats_result = await librosa_eng.beats(raw, filename)
            beat_times = beats_result.get("beats", [])
            if not beat_times:
                raise ValueError("no beats detected in audio")
            zip_bytes = await asyncio.to_thread(beat_slice, raw, filename, beat_times, output_format)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return {
            "zip_base64": base64.b64encode(zip_bytes).decode("ascii"),
            "beat_count": len(beat_times),
            "output_format": output_format,
        }

    # ── conv_reverb — convolution reverb ──────────────────────────────────

    @mcp.tool()
    async def convolution_reverb(
        file_path: str | None = None,
        file_url: str | None = None,
        ir_file_path: str | None = None,
        ir_file_url: str | None = None,
        wet_mix: float = 0.3,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Apply convolution reverb to audio using an impulse response (IR) file.
        wet_mix: 0.0 = dry only, 1.0 = wet only. Range [0.0, 1.0].
        Provide the IR via ir_file_path (staged) or ir_file_url (remote)."""
        if not (0.0 <= wet_mix <= 1.0):
            raise ValueError(f"wet_mix must be in [0.0, 1.0], got {wet_mix}")
        raw, filename = await _load_input(file_path, file_url)
        ir_raw, ir_filename = await _load_input(ir_file_path, ir_file_url, field_prefix="ir_file")
        try:
            result = await asyncio.to_thread(
                conv_reverb, raw, filename, ir_raw, ir_filename,
                wet_mix=wet_mix, output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(result, output_format, output_url)

    # ── transient — transient shaper ──────────────────────────────────────

    @mcp.tool()
    async def transient_shaper(
        file_path: str | None = None,
        file_url: str | None = None,
        attack_gain_db: float = 0.0,
        sustain_gain_db: float = 0.0,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """Shape transients via dual-compressor attack/sustain blending.
        attack_gain_db > 0 makes drums punchier; sustain_gain_db < 0 cuts room tail.
        Returns processed audio base64 or uploads to output_url."""
        raw, filename = await _load_input(file_path, file_url)
        try:
            result = await asyncio.to_thread(
                transient_shape, raw, filename,
                attack_gain_db=attack_gain_db,
                sustain_gain_db=sustain_gain_db,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(result, output_format, output_url)

    # ── dj_prep — BPM + key + LUFS + Camelot ─────────────────────────────

    @mcp.tool()
    async def dj_prep(
        file_path: str | None = None,
        file_url: str | None = None,
    ) -> dict[str, Any]:
        """Analyse a track for DJ use: BPM, musical key, Camelot wheel position,
        and integrated LUFS loudness. Requires librosa-analyze + chord-detect."""
        from .engines import is_beats_engine, is_chord_detect_engine, is_loudness_engine  # noqa: PLC0415
        _camelot: dict[str, str] = {
            "C major": "8B", "A minor": "8A", "G major": "9B", "E minor": "9A",
            "D major": "10B", "B minor": "10A", "A major": "11B", "F# minor": "11A",
            "E major": "12B", "C# minor": "12A", "B major": "1B", "G# minor": "1A",
            "F# major": "2B", "D# minor": "2A", "C# major": "3B", "A# minor": "3A",
            "G# major": "4B", "F minor": "4A", "D# major": "5B", "C minor": "5A",
            "A# major": "6B", "G minor": "6A", "F major": "7B", "D minor": "7A",
        }
        librosa_eng = engines.get("librosa-analyze")
        if librosa_eng is None or not is_beats_engine(librosa_eng):
            raise ValueError("librosa-analyze engine not configured")
        chord_eng = engines.get("chord-detect")
        if chord_eng is None or not is_chord_detect_engine(chord_eng):
            raise ValueError("chord-detect engine not configured")
        loudness_eng = next((e for e in engines.values() if is_loudness_engine(e)), None)
        raw, filename = await _load_input(file_path, file_url)
        try:
            beats_result = await librosa_eng.beats(raw, filename)
            chord_result = await chord_eng.detect_chords(raw, filename)
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        bpm = beats_result.get("tempo_bpm")
        key = chord_result.get("key", "")
        lufs: float | None = None
        if loudness_eng is not None:
            try:
                lufs = await loudness_eng.measure_lufs(raw, filename)
            except AudioConversionError:
                pass
        return {
            "bpm": round(bpm, 2) if bpm else None,
            "key": key,
            "camelot": _camelot.get(key, ""),
            "integrated_lufs": round(lufs, 2) if lufs is not None else None,
        }

    # ── jobs — list / poll / cancel async jobs ────────────────────────────

    @mcp.tool()
    async def list_jobs(status: str | None = None) -> dict[str, Any]:
        """List async jobs submitted to the job queue.
        status: filter by 'pending', 'running', 'completed', 'failed', 'cancelled'."""
        from .jobs import JOB_QUEUE  # noqa: PLC0415
        jobs = await JOB_QUEUE.list_jobs(status=status)
        return {"jobs": jobs}

    @mcp.tool()
    async def get_job(job_id: str) -> dict[str, Any]:
        """Get the status and result of an async job by ID."""
        from .jobs import JOB_QUEUE  # noqa: PLC0415
        job = await JOB_QUEUE.get(job_id)
        if job is None:
            raise ValueError(f"job {job_id!r} not found")
        return job.to_dict()

    @mcp.tool()
    async def cancel_job(job_id: str) -> dict[str, Any]:
        """Cancel a running async job or remove a completed job from the queue."""
        from .jobs import JOB_QUEUE  # noqa: PLC0415
        job = await JOB_QUEUE.get(job_id)
        if job is None:
            raise ValueError(f"job {job_id!r} not found")
        cancelled = await JOB_QUEUE.cancel(job_id)
        return {"job_id": job_id, "cancelled": cancelled}

    _log.info("mcp server initialised: 71 tools")
    return mcp
