"""FastAPI app — music-production REST API endpoints.

Endpoints:
  GET    /healthz                    unauthenticated liveness
  GET    /v1/engines                 list configured engines
  GET    /api/ps                     list currently loaded engines
  DELETE /api/ps/{engine}            evict one engine from memory
  POST   /unload                     evict all loaded engines
  POST   /v1/audio/separate          Demucs stem separation
  POST   /v1/audio/master            matchering / pedalboard-chain mastering
  POST   /v1/audio/analyze           librosa MIR analysis
  POST   /v1/audio/transform         pysox DSP transform chain
  POST   /v1/audio/loudness          pyloudnorm LUFS measurement + normalization
  GET    /v1/files                   list staged files
  PUT    /v1/files/{path}            stage a file
  GET    /v1/files/{path}            retrieve a staged file
  DELETE /v1/files/{path}            delete a staged file
  *      /v1/mcp                     MCP streamable-HTTP (mounted; tools mirror the REST surface)
"""

from __future__ import annotations

import asyncio
import json
import logging
import mimetypes
from contextlib import asynccontextmanager
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from . import config, files as files_mod
from .audio import (
    AudioConversionError,
    SUPPORTED_OUTPUT_FORMATS,
    content_type_for,
    multi_stream_zip,
)
from .auth import BearerAuthMiddleware
from .engines import build_engines, is_separation_engine, is_mastering_engine
from .engines import is_analysis_engine, is_transform_engine, is_loudness_engine
from .mcp_server import build_mcp_server
from .schema import AnalyzeResult, HealthResponse, LoudnessResult


log = logging.getLogger("audiolla.server")


def _resolve_device(req: str) -> str:
    if req != "auto":
        return req
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


REGISTRY = config.load_registry()
DEVICE = _resolve_device(config.DEVICE)
ENGINES = build_engines(REGISTRY, DEVICE)


async def _idle_sweeper() -> None:
    """Unload engines idle longer than AUDIOLLA_ENGINE_TTL."""
    while True:
        try:
            await asyncio.sleep(config.SWEEPER_INTERVAL_SECONDS)
            ttl = config.ENGINE_IDLE_TIMEOUT_SECONDS
            if ttl <= 0:
                continue
            for slug, engine in ENGINES.items():
                if not engine.loaded():
                    continue
                last = engine.last_used_secs_ago()
                if last is None:
                    continue
                if last < ttl:
                    continue
                log.info(
                    "idle sweeper: unloading %s (idle %.1fs >= %.1fs)",
                    slug, last, ttl,
                )
                try:
                    # Pass TTL so unload() re-checks the idle clock under
                    # its own lock — defends against the sweeper observing
                    # a stale idle value before another caller's _touch()
                    # is committed.
                    await engine.unload(if_idle_for=ttl)
                except Exception:  # noqa: BLE001
                    log.exception("idle sweeper: unload %s failed", slug)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("idle sweeper iteration failed")


_sweeper_task: asyncio.Task[None] | None = None

# Forward-declared so _lifespan can drive `MCP_SERVER.session_manager.run()`.
# Assigned to the real FastMCP instance below, before the app starts.
MCP_SERVER: Any = None


@asynccontextmanager
async def _lifespan(_app: FastAPI):
    files_mod.ensure_base(config.FILES_DIR)
    log.info(
        "audiolla starting: device=%s engines=%s ttl=%.0fs files_dir=%s auth=%s",
        DEVICE,
        list(ENGINES.keys()),
        config.ENGINE_IDLE_TIMEOUT_SECONDS,
        config.FILES_DIR,
        "on" if config.AUTH_TOKEN else "off",
    )

    for slug in config.PRELOAD:
        if slug not in ENGINES:
            log.warning("preload: unknown engine %s — skipping", slug)
            continue
        log.info("preload: %s", slug)
        try:
            await ENGINES[slug].get_model()
        except Exception:  # noqa: BLE001
            log.exception("preload %s failed", slug)

    global _sweeper_task
    _sweeper_task = asyncio.create_task(_idle_sweeper(), name="audiolla-sweeper")
    try:
        # MCP's streamable HTTP transport needs its session manager running
        # for the lifetime of the app.
        async with MCP_SERVER.session_manager.run():
            yield
    finally:
        if _sweeper_task is not None:
            _sweeper_task.cancel()
            try:
                await _sweeper_task
            except (asyncio.CancelledError, Exception):
                pass


app = FastAPI(
    title="audiolla",
    description=(
        "Self-hosted music-production REST API — stem separation, mastering, "
        "MIR analysis, DSP transforms, loudness normalization. "
        "OpenAPI 3.1-spec'd. Not OpenAI-compatible."
    ),
    lifespan=_lifespan,
)


class _MCPSlashRewriteMiddleware:
    """Rewrite ``/v1/mcp`` to ``/v1/mcp/`` before routing.

    Starlette's ``Mount("/v1/mcp", ...)`` serves requests at ``/v1/mcp/*``
    but emits a 307 redirect for the bare ``/v1/mcp`` form. Compliant
    clients re-POST to the new location; some MCP clients / curl scripts
    trip on it. Cheaper than docs churn over "remember the trailing slash".
    """

    def __init__(self, app: Any) -> None:
        self.app = app

    async def __call__(self, scope: Any, receive: Any, send: Any) -> None:
        if scope.get("type") == "http" and scope.get("path") == "/v1/mcp":
            scope = dict(scope)
            scope["path"] = "/v1/mcp/"
            scope["raw_path"] = b"/v1/mcp/"
        await self.app(scope, receive, send)


# Optional bearer auth covers every route — mounted MCP transport included.
app.add_middleware(BearerAuthMiddleware, token=config.AUTH_TOKEN)
# Outermost: normalise `/v1/mcp` → `/v1/mcp/` so the Mount's 307 redirect
# doesn't surprise non-strict clients.
app.add_middleware(_MCPSlashRewriteMiddleware)


@app.get("/healthz", response_model=HealthResponse)
def healthz() -> HealthResponse:
    return HealthResponse(ok=True, device=DEVICE, engines=list(ENGINES.keys()))


@app.get("/v1/engines")
def list_engines() -> dict[str, Any]:
    data = []
    for slug, engine in ENGINES.items():
        entry = REGISTRY[slug]
        info: dict[str, Any] = {
            "slug": slug,
            "executor": entry.get("executor", ""),
            "variant": entry.get("variant"),
            "stems": entry.get("stems"),
            "presets": entry.get("presets"),
            "description": entry.get("description", ""),
        }
        data.append(info)
    return {"object": "list", "data": data}


@app.get("/api/ps")
def list_loaded() -> dict[str, Any]:
    return {
        "engines": [
            {
                "slug": slug,
                "executor": REGISTRY[slug].get("executor", ""),
                "loaded": ENGINES[slug].loaded(),
                "idle_seconds": ENGINES[slug].last_used_secs_ago(),
            }
            for slug in ENGINES.keys()
            if ENGINES[slug].loaded()
        ]
    }


@app.delete("/api/ps/{engine:path}")
async def unload_one(engine: str) -> JSONResponse:
    decoded = unquote(engine)
    eng = ENGINES.get(decoded)
    if eng is None:
        return JSONResponse({"detail": f"unknown engine {decoded!r}"}, status_code=404)
    if not eng.loaded():
        return JSONResponse({"detail": "not loaded"}, status_code=404)
    await eng.unload()
    return JSONResponse({"unloaded": decoded}, status_code=200)


@app.post("/unload")
async def unload_all() -> dict[str, Any]:
    unloaded = []
    for slug, engine in ENGINES.items():
        if not engine.loaded():
            continue
        try:
            await engine.unload()
            unloaded.append(slug)
        except Exception:  # noqa: BLE001
            log.exception("unload %s failed", slug)
    return {"unloaded": unloaded}


def _validate_output_format(fmt: str) -> None:
    if fmt not in SUPPORTED_OUTPUT_FORMATS:
        raise HTTPException(
            status_code=415,
            detail=(
                f"unsupported output_format {fmt!r}; "
                f"supported: {sorted(SUPPORTED_OUTPUT_FORMATS)}"
            ),
        )


def _validate_target_lufs(target_lufs: float | None) -> None:
    """LUFS values outside roughly [-70, -0.1] are nonsensical — normalizing
    to -300 LUFS silences the audio entirely; +0 LUFS produces brick wall.
    Reject early with a clean 400 instead of letting the engine produce
    garbage with HTTP 200.
    """
    if target_lufs is None:
        return
    if not (-70.0 <= target_lufs <= -0.1):
        raise HTTPException(
            status_code=400,
            detail=(
                f"target_lufs must be in [-70.0, -0.1], got {target_lufs}"
            ),
        )


def _validate_engine_supports_device(slug: str) -> None:
    """Enforce ``engines.json`` ``cuda_only`` flag against the active device."""
    entry = REGISTRY.get(slug, {})
    if entry.get("cuda_only") and not DEVICE.startswith("cuda"):
        raise HTTPException(
            status_code=400,
            detail=(
                f"engine {slug!r} is cuda_only — the server is running on "
                f"{DEVICE!r}. Run the CUDA image (psyb0t/audiolla:local-cuda) "
                "with --gpus all to enable this engine."
            ),
        )


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"upload too large ({len(raw)} bytes > {config.MAX_UPLOAD_BYTES})",
        )
    if not raw:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    return raw, file.filename or "audio"


async def _evict_siblings(current_slug: str) -> None:
    siblings = [
        (slug, e) for slug, e in ENGINES.items()
        if slug != current_slug and e.loaded()
    ]
    if not siblings:
        return
    log.info(
        "evicting %d sibling engine(s) before loading %s: %s",
        len(siblings), current_slug, [slug for slug, _ in siblings],
    )
    await asyncio.gather(*(e.unload() for _, e in siblings), return_exceptions=True)


@app.post("/v1/audio/separate")
async def separate(
    file: UploadFile = File(...),
    engine: str = Form(...),
    stems: list[str] = Form(default=[]),
    output_format: str = Form(default="wav"),
) -> Response:
    _validate_output_format(output_format)

    eng = ENGINES.get(engine)
    if eng is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown engine {engine!r}; configured: {list(ENGINES.keys())}",
        )
    if not is_separation_engine(eng):
        raise HTTPException(
            status_code=400,
            detail=f"engine {engine!r} does not support stem separation",
        )
    _validate_engine_supports_device(engine)

    raw, filename = await _read_upload(file)

    entry = REGISTRY[engine]
    available_stems = entry.get("stems", [])
    requested = stems if stems else available_stems
    invalid = [s for s in requested if s not in available_stems]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"unknown stems {invalid} for engine {engine!r}; available: {available_stems}",
        )

    await _evict_siblings(engine)

    try:
        stem_results = await eng.separate(
            raw, filename, stems=requested, output_format=output_format
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if len(requested) == 1:
        stem_name = requested[0]
        audio_bytes = stem_results[stem_name]
        ct = content_type_for(output_format)
        return Response(
            content=audio_bytes,
            media_type=ct,
            headers={
                "Content-Disposition": f'attachment; filename="{stem_name}.{output_format}"'
            },
        )

    return Response(
        content=multi_stream_zip(stem_results, output_format),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{engine}-stems.zip"'},
    )


@app.post("/v1/audio/master")
async def master(
    file: UploadFile = File(...),
    mode: str = Form(...),
    reference: UploadFile | None = File(default=None),
    preset: str | None = Form(default=None),
    target_lufs: float | None = Form(default=None),
    output_format: str = Form(default="wav"),
) -> Response:
    _validate_output_format(output_format)

    if mode not in ("reference", "chain"):
        raise HTTPException(
            status_code=400, detail="mode must be 'reference' or 'chain'"
        )
    if mode == "reference" and (reference is None or not reference.filename):
        raise HTTPException(
            status_code=400, detail="mode=reference requires a reference file"
        )
    if mode == "chain" and not preset:
        raise HTTPException(
            status_code=400, detail="mode=chain requires a preset name"
        )
    _validate_target_lufs(target_lufs)

    raw, filename = await _read_upload(file)

    if mode == "reference":
        engine_slug = "matchering"
        eng = ENGINES.get(engine_slug)
        if eng is None:
            raise HTTPException(
                status_code=404, detail="matchering engine not configured"
            )
        if not is_mastering_engine(eng):
            raise HTTPException(
                status_code=400, detail="matchering engine does not support mastering"
            )
        # Belt-and-braces re-check: the mode=reference guard above already
        # rejected None, but `assert` would be stripped under python -O so we
        # raise an explicit HTTPException to survive optimised builds.
        if reference is None:
            raise HTTPException(
                status_code=400, detail="mode=reference requires a reference file"
            )
        ref_raw, ref_filename = await _read_upload(reference)
        await _evict_siblings(engine_slug)
        try:
            audio_bytes = await eng.master_reference(
                raw, filename, ref_raw, ref_filename,
                target_lufs=target_lufs, output_format=output_format,
            )
        except AudioConversionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        engine_slug = "pedalboard-chain"
        eng = ENGINES.get(engine_slug)
        if eng is None:
            raise HTTPException(
                status_code=404, detail="pedalboard-chain engine not configured"
            )
        if not is_mastering_engine(eng):
            raise HTTPException(
                status_code=400, detail="pedalboard-chain engine does not support mastering"
            )
        available_presets = REGISTRY[engine_slug].get("presets", [])
        if preset not in available_presets:
            raise HTTPException(
                status_code=400,
                detail=f"unknown preset {preset!r}; available: {available_presets}",
            )
        await _evict_siblings(engine_slug)
        try:
            audio_bytes = await eng.master_chain(
                raw, filename,
                preset=preset, target_lufs=target_lufs, output_format=output_format,
            )
        except AudioConversionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=audio_bytes,
        media_type=content_type_for(output_format),
        headers={"Content-Disposition": f'attachment; filename="mastered.{output_format}"'},
    )


@app.post("/v1/audio/analyze", response_model=AnalyzeResult)
async def analyze(
    file: UploadFile = File(...),
    features: list[str] = Form(default=[]),
) -> AnalyzeResult:
    _VALID_FEATURES = frozenset({
        "bpm", "key", "loudness", "duration", "spectral_centroid", "rms", "zcr"
    })
    if features:
        invalid = [f for f in features if f not in _VALID_FEATURES]
        if invalid:
            raise HTTPException(
                status_code=400,
                detail=f"unknown features {invalid}; valid: {sorted(_VALID_FEATURES)}",
            )
    requested_features = list(features) if features else list(_VALID_FEATURES)

    engine_slug = "librosa-analyze"
    eng = ENGINES.get(engine_slug)
    if eng is None:
        raise HTTPException(
            status_code=404, detail="librosa-analyze engine not configured"
        )
    if not is_analysis_engine(eng):
        raise HTTPException(
            status_code=400, detail="librosa-analyze engine does not support analysis"
        )

    raw, filename = await _read_upload(file)

    try:
        result = await eng.analyze(raw, filename, features=requested_features)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AnalyzeResult(**result)


@app.post("/v1/audio/transform")
async def transform(
    file: UploadFile = File(...),
    operations: str = Form(...),
    output_format: str = Form(default="wav"),
) -> Response:
    _validate_output_format(output_format)

    try:
        ops = json.loads(operations)
        if not isinstance(ops, list):
            raise ValueError("operations must be a JSON array")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"invalid operations JSON: {exc}",
        ) from exc

    _VALID_OPS = frozenset({
        "gain", "equalizer", "compand", "reverb", "pitch",
        "tempo", "rate", "channels", "trim", "pad",
    })
    for op_item in ops:
        if not isinstance(op_item, dict) or "op" not in op_item:
            raise HTTPException(
                status_code=400,
                detail="each operation must be an object with 'op' key",
            )
        if op_item["op"] not in _VALID_OPS:
            raise HTTPException(
                status_code=400,
                detail=f"unknown op {op_item['op']!r}; valid: {sorted(_VALID_OPS)}",
            )

    engine_slug = "sox-transform"
    eng = ENGINES.get(engine_slug)
    if eng is None:
        raise HTTPException(
            status_code=404, detail="sox-transform engine not configured"
        )
    if not is_transform_engine(eng):
        raise HTTPException(
            status_code=400, detail="sox-transform engine does not support transforms"
        )

    raw, filename = await _read_upload(file)

    try:
        audio_bytes = await eng.transform(
            raw, filename, operations=ops, output_format=output_format
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=audio_bytes,
        media_type=content_type_for(output_format),
        headers={"Content-Disposition": f'attachment; filename="transformed.{output_format}"'},
    )


@app.post("/v1/audio/loudness")
async def loudness(
    file: UploadFile = File(...),
    target_lufs: float | None = Form(default=None),
    output_format: str = Form(default="wav"),
) -> Any:
    _validate_output_format(output_format)
    _validate_target_lufs(target_lufs)

    engine_slug = "librosa-analyze"
    eng = ENGINES.get(engine_slug)
    if eng is None:
        raise HTTPException(
            status_code=404, detail="librosa-analyze engine not configured"
        )
    if not is_loudness_engine(eng):
        raise HTTPException(
            status_code=400, detail="engine does not support loudness operations"
        )

    raw, filename = await _read_upload(file)

    if target_lufs is None:
        try:
            lufs = await eng.measure_lufs(raw, filename)
        except AudioConversionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return LoudnessResult(
            loudness_lufs=lufs, target_lufs=None, normalized=False
        )

    try:
        audio_bytes, lufs = await eng.normalize_lufs(
            raw, filename, target_lufs=target_lufs, output_format=output_format
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Response(
        content=audio_bytes,
        media_type=content_type_for(output_format),
        headers={
            "Content-Disposition": f'attachment; filename="normalized.{output_format}"',
            "X-Loudness-LUFS": str(lufs),
            "X-Target-LUFS": str(target_lufs),
        },
    )


def _resolve_files_path(raw: str) -> tuple[Any, str]:
    try:
        rel = files_mod.sanitize_path(raw)
        return files_mod.resolve_under(config.FILES_DIR, rel), str(rel)
    except files_mod.FilePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/v1/files")
def files_list() -> dict[str, Any]:
    return {"files": files_mod.list_files(config.FILES_DIR)}


@app.put("/v1/files/{path:path}")
async def files_put(path: str, request: Request) -> JSONResponse:
    dest, rel_str = _resolve_files_path(path)
    body = await request.body()
    if len(body) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"upload too large ({len(body)} bytes > {config.MAX_UPLOAD_BYTES})",
        )
    await asyncio.to_thread(files_mod.write_atomic, dest, body)
    return JSONResponse({"path": rel_str, "size": len(body)}, status_code=201)


@app.get("/v1/files/{path:path}")
def files_get(path: str) -> FileResponse:
    src, rel_str = _resolve_files_path(path)
    if src.is_symlink() or not src.is_file():
        raise HTTPException(status_code=404, detail=f"file not found: {rel_str}")
    mime, _ = mimetypes.guess_type(src.name)
    return FileResponse(
        path=str(src),
        media_type=mime or "application/octet-stream",
        filename=src.name,
    )


@app.delete("/v1/files/{path:path}")
def files_delete(path: str) -> JSONResponse:
    target, rel_str = _resolve_files_path(path)
    if target.is_symlink() or not target.is_file():
        raise HTTPException(status_code=404, detail=f"file not found: {rel_str}")
    try:
        target.unlink()
    except OSError as exc:
        raise HTTPException(status_code=500, detail=f"unlink failed: {exc}") from exc
    files_mod.prune_empty_parents(target, config.FILES_DIR)
    return JSONResponse({"deleted": rel_str}, status_code=200)


# ── MCP server mounted at /v1/mcp ────────────────────────────────────────────
# FastMCP's streamable-HTTP transport. Tools mirror the REST surface so an
# LLM agent can drive audiolla over JSON-RPC. ``streamable_http_path = "/"``
# is set in build_mcp_server so the mount at "/v1/mcp" doesn't double-prefix.
# Built once here so the lifespan can `async with MCP_SERVER.session_manager.run()`.

MCP_SERVER = build_mcp_server(engines=ENGINES, registry=REGISTRY)
app.mount("/v1/mcp", MCP_SERVER.streamable_http_app())
