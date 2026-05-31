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

from . import config, fetch, files as files_mod
from .audio import AudioConversionError, content_type_for


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
        file_path: str | None, file_url: str | None,
        *, field_prefix: str = "file",
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
        data: bytes, output_format: str, output_url: str | None,
    ) -> dict[str, Any]:
        """Return audio either base64-encoded (default) or as a presigned-PUT
        upload confirmation when output_url is set."""
        if output_url:
            try:
                await fetch.upload_bytes(
                    output_url, data, content_type_for(output_format),
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
                reference_path, reference_url, field_prefix="reference",
            )
            try:
                audio = await eng.master_reference(
                    raw, name, ref_raw, ref_name,
                    target_lufs=target_lufs, output_format=output_format,
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
                    raw, name,
                    preset=preset, target_lufs=target_lufs,
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
            result = await eng.analyze(
                raw, name, features=features or []
            )
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
                raw, name, operations=operations,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return await _emit_audio(audio, output_format, output_url)

    @mcp.tool()
    async def loudness(
        file_path: str | None = None,
        file_url: str | None = None,
        target_lufs: float | None = None,
        output_format: str = "wav",
        output_url: str | None = None,
    ) -> dict[str, Any]:
        """pyloudnorm LUFS analyze (no target_lufs) or normalize (with).

        Provide exactly one of `file_path` or `file_url`. Without
        `target_lufs`, returns the measurement as JSON. With
        `target_lufs`, returns the normalized audio (base64 by default,
        or PUT to `output_url`) plus the measured LUFS.
        """
        raw, name = await _load_input(file_path, file_url)
        eng = engines.get("librosa-analyze")
        if eng is None or not hasattr(eng, "measure_lufs"):
            raise ValueError("loudness engine not configured")
        if target_lufs is None:
            try:
                lufs = await eng.measure_lufs(raw, name)
            except AudioConversionError as exc:
                raise ValueError(str(exc)) from exc
            return {
                "loudness_lufs": lufs,
                "target_lufs": None,
                "normalized": False,
            }
        try:
            audio, measured = await eng.normalize_lufs(
                raw, name, target_lufs=target_lufs,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        emitted = await _emit_audio(audio, output_format, output_url)
        emitted["measured_lufs"] = measured
        emitted["target_lufs"] = target_lufs
        emitted["normalized"] = True
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
                raw, name, effects=effects, output_format=output_format,
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
                raw, name,
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
            raise ValueError(
                "midi-compose and midi-render must both be configured"
            )
        try:
            midi = await compose_eng.compose(spec)
            audio = await render_eng.render(
                midi, "composed.mid",
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
            raise ValueError(
                f"content_base64 is not valid base64: {exc}"
            ) from exc
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise ValueError(
                f"upload too large ({len(data)} bytes > "
                f"{config.MAX_UPLOAD_BYTES})"
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

    _log.info("mcp server initialised: 10 tools")
    return mcp
