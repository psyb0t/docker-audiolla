"""MCP server for audiolla — mounted at ``/v1/mcp`` on the main FastAPI app.

Exposes the same surface as the HTTP REST API as MCP tools so an agent can
drive audiolla over JSON-RPC / streamable-HTTP. Tools:

  - ``list_engines``   — what engines are loadable
  - ``separate``       — run Demucs stem separation on a staged file
  - ``master``         — matchering reference + pedalboard chain mastering
  - ``analyze``        — librosa MIR feature extraction
  - ``transform``      — pysox DSP chain
  - ``loudness``       — pyloudnorm analyze / normalize
  - ``list_files``     — what's currently staged
  - ``put_file``       — upload a file (base64-encoded body)
  - ``get_file``       — read a staged file (base64-encoded body back)
  - ``delete_file``    — remove a staged file

Audio I/O over MCP is base64-in / base64-out (or staged-file paths). MCP
JSON-RPC can't carry raw bytes — `content_base64` round-trips through the
client.

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

from . import config, files as files_mod
from .audio import AudioConversionError


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
            "mastering, MIR analysis, DSP transform, loudness. Upload "
            "audio via put_file (base64), then call separate / master / "
            "analyze / transform / loudness with the staged path. Use "
            "get_file to retrieve processed outputs (also base64)."
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
        file_path: str,
        engine: str,
        stems: list[str],
        output_format: str = "wav",
    ) -> dict[str, Any]:
        """Demucs stem separation. Returns base64-encoded stems."""
        raw, _ = _load_staged(file_path)
        eng = engines.get(engine)
        if eng is None or not hasattr(eng, "separate"):
            raise ValueError(
                f"engine {engine!r} not configured or doesn't support separation"
            )
        try:
            result = await eng.separate(
                raw, file_path, stems=stems, output_format=output_format
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return {
            "stems": {
                name: base64.b64encode(audio).decode("ascii")
                for name, audio in result.items()
            },
            "output_format": output_format,
        }

    @mcp.tool()
    async def master(
        file_path: str,
        mode: str,
        reference_path: str | None = None,
        preset: str | None = None,
        target_lufs: float | None = None,
        output_format: str = "wav",
    ) -> dict[str, Any]:
        """Master audio. mode='reference' (matchering) or 'chain' (pedalboard)."""
        raw, _ = _load_staged(file_path)
        if mode == "reference":
            if not reference_path:
                raise ValueError("mode=reference requires reference_path")
            ref_raw, _ = _load_staged(reference_path)
            eng = engines.get("matchering")
            if eng is None:
                raise ValueError("matchering engine not configured")
            try:
                audio = await eng.master_reference(
                    raw, file_path, ref_raw, reference_path,
                    target_lufs=target_lufs, output_format=output_format,
                )
            except AudioConversionError as exc:
                raise ValueError(str(exc)) from exc
        elif mode == "chain":
            if not preset:
                raise ValueError("mode=chain requires preset")
            eng = engines.get("pedalboard-chain")
            if eng is None:
                raise ValueError("pedalboard-chain engine not configured")
            try:
                audio = await eng.master_chain(
                    raw, file_path,
                    preset=preset, target_lufs=target_lufs,
                    output_format=output_format,
                )
            except AudioConversionError as exc:
                raise ValueError(str(exc)) from exc
        else:
            raise ValueError("mode must be 'reference' or 'chain'")
        return {
            "audio_base64": base64.b64encode(audio).decode("ascii"),
            "output_format": output_format,
        }

    @mcp.tool()
    async def analyze(
        file_path: str,
        features: list[str] | None = None,
    ) -> dict[str, Any]:
        """librosa MIR analysis. Returns extracted features as JSON."""
        raw, _ = _load_staged(file_path)
        eng = engines.get("librosa-analyze")
        if eng is None:
            raise ValueError("librosa-analyze engine not configured")
        try:
            result = await eng.analyze(
                raw, file_path, features=features or []
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return result

    @mcp.tool()
    async def transform(
        file_path: str,
        operations: list[dict[str, Any]],
        output_format: str = "wav",
    ) -> dict[str, Any]:
        """pysox DSP transform chain. operations is a list of {op, params}."""
        raw, _ = _load_staged(file_path)
        eng = engines.get("sox-transform")
        if eng is None:
            raise ValueError("sox-transform engine not configured")
        try:
            audio = await eng.transform(
                raw, file_path, operations=operations,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return {
            "audio_base64": base64.b64encode(audio).decode("ascii"),
            "output_format": output_format,
        }

    @mcp.tool()
    async def loudness(
        file_path: str,
        target_lufs: float | None = None,
        output_format: str = "wav",
    ) -> dict[str, Any]:
        """pyloudnorm LUFS analyze (no target_lufs) or normalize (with target)."""
        raw, _ = _load_staged(file_path)
        eng = engines.get("librosa-analyze")
        if eng is None or not hasattr(eng, "measure_lufs"):
            raise ValueError("loudness engine not configured")
        if target_lufs is None:
            try:
                lufs = await eng.measure_lufs(raw, file_path)
            except AudioConversionError as exc:
                raise ValueError(str(exc)) from exc
            return {
                "loudness_lufs": lufs,
                "target_lufs": None,
                "normalized": False,
            }
        try:
            audio, measured = await eng.normalize_lufs(
                raw, file_path, target_lufs=target_lufs,
                output_format=output_format,
            )
        except AudioConversionError as exc:
            raise ValueError(str(exc)) from exc
        return {
            "audio_base64": base64.b64encode(audio).decode("ascii"),
            "output_format": output_format,
            "measured_lufs": measured,
            "target_lufs": target_lufs,
            "normalized": True,
        }

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
