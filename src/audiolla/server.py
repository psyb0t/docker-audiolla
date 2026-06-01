"""FastAPI app — music-production REST API endpoints.

Endpoints:
  GET    /healthz                    unauthenticated liveness
  GET    /v1/engines                 list configured engines
  GET    /v1/ps                      list currently loaded engines
  DELETE /v1/ps/{engine}             evict one engine from memory
  POST   /v1/unload                  evict all loaded engines
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

Audio endpoints accept exactly one of three input modes:
  - file       (multipart upload)
  - file_path  (relative path under FILES_DIR / staging)
  - file_url   (remote URL, subject to AUDIOLLA_FETCH_MODE policy)

Audio-producing endpoints also accept optional output_path / output_url
to write the result to staging or PUT to a presigned URL instead of
returning bytes inline. See input_resolver.py / output_writer.py.
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
from .engines import is_fx_engine, is_midi_compose_engine, is_midi_render_engine
from .engines import is_beats_engine, is_onsets_engine, is_melody_engine
from .engines import is_segments_engine, is_silence_engine, is_ffmpeg_render_engine
from .engines import is_fingerprint_engine, is_midi_inspect_engine
from .engines import is_midi_transform_engine
from .engines.ffmpeg_render import visualize_modes
from .input_resolver import resolve_input
from .mcp_server import build_mcp_server
from .output_writer import write_output
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


@app.get("/v1/ps")
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


@app.delete("/v1/ps/{engine:path}")
async def unload_one(engine: str) -> JSONResponse:
    decoded = unquote(engine)
    eng = ENGINES.get(decoded)
    if eng is None:
        return JSONResponse({"detail": f"unknown engine {decoded!r}"}, status_code=404)
    if not eng.loaded():
        return JSONResponse({"detail": "not loaded"}, status_code=404)
    await eng.unload()
    return JSONResponse({"unloaded": decoded}, status_code=200)


@app.post("/v1/unload")
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
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
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

    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )

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
        return await write_output(
            audio_bytes,
            media_type=content_type_for(output_format),
            filename=f"{stem_name}.{output_format}",
            output_path=output_path,
            output_url=output_url,
            extra_json={
                "engine": engine,
                "stem": stem_name,
                "output_format": output_format,
            },
        )

    return await write_output(
        multi_stream_zip(stem_results, output_format),
        media_type="application/zip",
        filename=f"{engine}-stems.zip",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "engine": engine,
            "stems": list(stem_results.keys()),
            "output_format": output_format,
        },
    )


@app.post("/v1/audio/master")
async def master(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    mode: str = Form(...),
    reference: UploadFile | None = File(default=None),
    reference_path: str | None = Form(default=None),
    reference_url: str | None = Form(default=None),
    preset: str | None = Form(default=None),
    target_lufs: float | None = Form(default=None),
    output_format: str = Form(default="wav"),
) -> Response:
    _validate_output_format(output_format)

    if mode not in ("reference", "chain"):
        raise HTTPException(
            status_code=400, detail="mode must be 'reference' or 'chain'"
        )
    if mode == "chain" and not preset:
        raise HTTPException(
            status_code=400, detail="mode=chain requires a preset name"
        )
    _validate_target_lufs(target_lufs)

    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )

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
        ref_raw, ref_filename = await resolve_input(
            file=reference,
            file_path=reference_path,
            file_url=reference_url,
            field_prefix="reference",
        )
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

    return await write_output(
        audio_bytes,
        media_type=content_type_for(output_format),
        filename=f"mastered.{output_format}",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "engine": engine_slug,
            "mode": mode,
            "output_format": output_format,
        },
    )


@app.post("/v1/audio/analyze", response_model=AnalyzeResult)
async def analyze(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
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

    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )

    try:
        result = await eng.analyze(raw, filename, features=requested_features)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return AnalyzeResult(**result)


@app.post("/v1/audio/transform")
async def transform(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
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

    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )

    try:
        audio_bytes = await eng.transform(
            raw, filename, operations=ops, output_format=output_format
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await write_output(
        audio_bytes,
        media_type=content_type_for(output_format),
        filename=f"transformed.{output_format}",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "engine": engine_slug,
            "operations": ops,
            "output_format": output_format,
        },
    )


@app.post("/v1/audio/loudness")
async def loudness(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
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

    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )

    if target_lufs is None:
        # Pure measurement — JSON only, output_path/url are meaningless.
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

    return await write_output(
        audio_bytes,
        media_type=content_type_for(output_format),
        filename=f"normalized.{output_format}",
        output_path=output_path,
        output_url=output_url,
        extra_inline_headers={
            "X-Loudness-LUFS": str(lufs),
            "X-Target-LUFS": str(target_lufs),
        },
        extra_json={
            "measured_lufs": lufs,
            "target_lufs": target_lufs,
            "output_format": output_format,
        },
    )


# ── /v1/audio/fx — generic pedalboard chain ─────────────────────────────────


@app.post("/v1/audio/fx")
async def fx(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    effects: str = Form(...),
    output_format: str = Form(default="wav"),
) -> Response:
    _validate_output_format(output_format)

    try:
        chain = json.loads(effects)
        if not isinstance(chain, list):
            raise ValueError("effects must be a JSON array")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=400, detail=f"invalid effects JSON: {exc}",
        ) from exc

    engine_slug = "fx-chain"
    eng = ENGINES.get(engine_slug)
    if eng is None:
        raise HTTPException(
            status_code=404, detail="fx-chain engine not configured",
        )
    if not is_fx_engine(eng):
        raise HTTPException(
            status_code=400, detail="fx-chain engine does not support fx",
        )

    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )

    try:
        audio_bytes = await eng.fx(
            raw, filename, effects=chain, output_format=output_format,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await write_output(
        audio_bytes,
        media_type=content_type_for(output_format),
        filename=f"fx.{output_format}",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "engine": engine_slug,
            "effects": chain,
            "output_format": output_format,
        },
    )


# ── /v1/midi/compose — JSON spec → MIDI bytes ───────────────────────────────


@app.post("/v1/midi/compose")
async def midi_compose(
    request: Request,
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
) -> Response:
    """JSON-to-MIDI transcoder.

    Body is application/json with the song spec (see midi_compose engine
    docstring). The two output mode form fields are accepted as query
    params too — Form() reads multipart; we also accept the JSON body
    when Content-Type is application/json. To pass output_path/url with
    a JSON body, set them as query parameters: ?output_path=...
    """
    # Accept either JSON body (recommended) or multipart form with a
    # `spec` field. JSON body is the natural shape for LLM agents.
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            spec = await request.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid JSON body: {exc}",
            ) from exc
        # Query params override Form defaults when the body is JSON.
        output_path = request.query_params.get("output_path") or output_path
        output_url = request.query_params.get("output_url") or output_url
    else:
        form = await request.form()
        spec_raw = form.get("spec")
        if not spec_raw:
            raise HTTPException(
                status_code=400,
                detail="POST application/json with the spec body, "
                "or multipart with a `spec` field carrying JSON.",
            )
        try:
            spec = json.loads(str(spec_raw))
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid `spec` JSON: {exc}",
            ) from exc
        output_path = (form.get("output_path") or output_path or None)  # type: ignore[assignment]
        output_url = (form.get("output_url") or output_url or None)  # type: ignore[assignment]
        if output_path is not None:
            output_path = str(output_path) or None
        if output_url is not None:
            output_url = str(output_url) or None

    engine_slug = "midi-compose"
    eng = ENGINES.get(engine_slug)
    if eng is None:
        raise HTTPException(
            status_code=404, detail="midi-compose engine not configured",
        )
    if not is_midi_compose_engine(eng):
        raise HTTPException(
            status_code=400, detail="midi-compose engine missing compose()",
        )

    try:
        midi_bytes = await eng.compose(spec)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await write_output(
        midi_bytes,
        media_type="audio/midi",
        filename="composed.mid",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "engine": engine_slug,
            "size": len(midi_bytes),
        },
    )


# ── /v1/midi/render — MIDI → audio via fluidsynth ───────────────────────────


@app.post("/v1/midi/render")
async def midi_render(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    soundfont_path: str | None = Form(default=None),
    gain: float = Form(default=0.5),
    samplerate: int = Form(default=44100),
    output_format: str = Form(default="wav"),
) -> Response:
    _validate_output_format(output_format)

    engine_slug = "midi-render"
    eng = ENGINES.get(engine_slug)
    if eng is None:
        raise HTTPException(
            status_code=404, detail="midi-render engine not configured",
        )
    if not is_midi_render_engine(eng):
        raise HTTPException(
            status_code=400, detail="midi-render engine missing render()",
        )

    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )

    try:
        audio_bytes = await eng.render(
            raw, filename,
            soundfont_path=soundfont_path,
            output_format=output_format,
            gain=gain,
            samplerate=samplerate,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await write_output(
        audio_bytes,
        media_type=content_type_for(output_format),
        filename=f"rendered.{output_format}",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "engine": engine_slug,
            "output_format": output_format,
            "soundfont_path": soundfont_path,
        },
    )


# ── /v1/midi/generate — compose + render in one call ────────────────────────


@app.post("/v1/midi/generate")
async def midi_generate(
    request: Request,
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    output_format: str = Form(default="wav"),
    soundfont_path: str | None = Form(default=None),
    gain: float = Form(default=0.5),
    samplerate: int = Form(default=44100),
) -> Response:
    """Compose MIDI from a JSON spec, then immediately render it to audio.

    Body shape is the same as ``/v1/midi/compose`` (the song spec). The
    `output_format`, `soundfont_path`, `gain`, `samplerate`, `output_path`,
    `output_url` knobs come from the query string when the body is JSON,
    or from multipart Form fields when it isn't.
    """
    _validate_output_format(output_format)

    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            spec = await request.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid JSON body: {exc}",
            ) from exc
        # Query-param overrides for the side knobs.
        q = request.query_params
        if q.get("output_format"):
            output_format = q["output_format"]
            _validate_output_format(output_format)
        if q.get("soundfont_path"):
            soundfont_path = q["soundfont_path"]
        if q.get("gain"):
            try:
                gain = float(q["gain"])
            except ValueError:
                raise HTTPException(
                    status_code=400, detail=f"gain must be a number: {q['gain']!r}",
                )
        if q.get("samplerate"):
            try:
                samplerate = int(q["samplerate"])
            except ValueError:
                raise HTTPException(
                    status_code=400,
                    detail=f"samplerate must be an int: {q['samplerate']!r}",
                )
        output_path = q.get("output_path") or output_path
        output_url = q.get("output_url") or output_url
    else:
        form = await request.form()
        spec_raw = form.get("spec")
        if not spec_raw:
            raise HTTPException(
                status_code=400,
                detail="POST application/json with the spec body, "
                "or multipart with a `spec` field carrying JSON.",
            )
        try:
            spec = json.loads(str(spec_raw))
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid `spec` JSON: {exc}",
            ) from exc

    compose_eng = ENGINES.get("midi-compose")
    render_eng = ENGINES.get("midi-render")
    if compose_eng is None or render_eng is None:
        raise HTTPException(
            status_code=404,
            detail="midi-compose and midi-render must both be configured",
        )

    try:
        midi_bytes = await compose_eng.compose(spec)
        audio_bytes = await render_eng.render(
            midi_bytes, "composed.mid",
            soundfont_path=soundfont_path,
            output_format=output_format,
            gain=gain,
            samplerate=samplerate,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await write_output(
        audio_bytes,
        media_type=content_type_for(output_format),
        filename=f"generated.{output_format}",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "engine": "midi-generate",
            "output_format": output_format,
            "midi_size": len(midi_bytes),
        },
    )


# ── /v1/audio/beats — librosa beat tracking + optional click track ──────────


@app.post("/v1/audio/beats")
async def beats(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    click_track: bool = Form(default=False),
    output_format: str = Form(default="wav"),
) -> Any:
    """Returns JSON with tempo + beat positions. With ``click_track=true``
    also synthesises a metronome-mixed audio render and includes a
    base64-encoded copy in the JSON.
    """
    _validate_output_format(output_format)
    eng = ENGINES.get("librosa-analyze")
    if eng is None or not is_beats_engine(eng):
        raise HTTPException(
            status_code=404, detail="librosa-analyze engine not configured",
        )
    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )
    try:
        result = await eng.beats(
            raw, filename,
            click_track=click_track,
            output_format=output_format,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if click_track and (output_path or output_url):
        # Caller wants the audio routed out-of-band; pull it from the
        # engine response and use write_output. JSON still carries
        # beats / tempo so the caller gets both.
        import base64 as _b64
        audio_bytes = _b64.b64decode(result.pop("click_track_base64"))
        return await write_output(
            audio_bytes,
            media_type=content_type_for(output_format),
            filename=f"clicks.{output_format}",
            output_path=output_path,
            output_url=output_url,
            extra_json=result,
        )
    return result


# ── /v1/audio/onsets — librosa onset detection ──────────────────────────────


@app.post("/v1/audio/onsets")
async def onsets(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
) -> dict[str, Any]:
    eng = ENGINES.get("librosa-analyze")
    if eng is None or not is_onsets_engine(eng):
        raise HTTPException(
            status_code=404, detail="librosa-analyze engine not configured",
        )
    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )
    try:
        return await eng.onsets(raw, filename)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── /v1/audio/melody — pyin pitch contour + optional MIDI quantize ──────────


@app.post("/v1/audio/melody")
async def melody(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    fmin: float = Form(default=65.0),
    fmax: float = Form(default=2093.0),
    as_midi: bool = Form(default=False),
) -> Any:
    eng = ENGINES.get("librosa-analyze")
    if eng is None or not is_melody_engine(eng):
        raise HTTPException(
            status_code=404, detail="librosa-analyze engine not configured",
        )
    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )
    try:
        result = await eng.melody(
            raw, filename, fmin=fmin, fmax=fmax, as_midi=as_midi,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if as_midi and (output_path or output_url):
        import base64 as _b64
        midi_bytes = _b64.b64decode(result.pop("midi_base64"))
        result.pop("midi_size", None)
        return await write_output(
            midi_bytes,
            media_type="audio/midi",
            filename="melody.mid",
            output_path=output_path,
            output_url=output_url,
            extra_json=result,
        )
    return result


# ── /v1/audio/segments — music-structure segmentation ──────────────────────


@app.post("/v1/audio/segments")
async def segments(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    num_segments: int = Form(default=6),
) -> dict[str, Any]:
    eng = ENGINES.get("librosa-analyze")
    if eng is None or not is_segments_engine(eng):
        raise HTTPException(
            status_code=404, detail="librosa-analyze engine not configured",
        )
    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )
    try:
        return await eng.segments(raw, filename, num_segments=num_segments)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── /v1/audio/silence — ffmpeg silencedetect + optional auto-trim ──────────


@app.post("/v1/audio/silence")
async def silence(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    threshold_db: float = Form(default=-30.0),
    min_duration_sec: float = Form(default=0.5),
    trim_mode: str | None = Form(default=None),
    output_format: str = Form(default="wav"),
) -> Any:
    _validate_output_format(output_format)
    eng = ENGINES.get("silence-detect")
    if eng is None or not is_silence_engine(eng):
        raise HTTPException(
            status_code=404, detail="silence-detect engine not configured",
        )
    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )
    try:
        result = await eng.detect(
            raw, filename,
            threshold_db=threshold_db,
            min_duration_sec=min_duration_sec,
            trim_mode=trim_mode,
            output_format=output_format,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if trim_mode and (output_path or output_url):
        import base64 as _b64
        audio_bytes = _b64.b64decode(result.pop("trimmed_audio_base64"))
        return await write_output(
            audio_bytes,
            media_type=content_type_for(output_format),
            filename=f"trimmed.{output_format}",
            output_path=output_path,
            output_url=output_url,
            extra_json=result,
        )
    return result


# ── /v1/audio/spectrogram — static PNG via ffmpeg showspectrumpic ──────────


@app.post("/v1/audio/spectrogram")
async def spectrogram(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    width: int = Form(default=1920),
    height: int = Form(default=1080),
    color: str = Form(default="intensity"),
    scale: str = Form(default="log"),
) -> Response:
    eng = ENGINES.get("ffmpeg-render")
    if eng is None or not is_ffmpeg_render_engine(eng):
        raise HTTPException(
            status_code=404, detail="ffmpeg-render engine not configured",
        )
    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )
    try:
        png = await eng.spectrogram(
            raw, filename, width=width, height=height, color=color, scale=scale,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await write_output(
        png,
        media_type="image/png",
        filename="spectrogram.png",
        output_path=output_path,
        output_url=output_url,
        extra_json={"engine": "ffmpeg-render", "kind": "spectrogram"},
    )


# ── /v1/audio/waveform — static PNG via ffmpeg showwavespic ────────────────


@app.post("/v1/audio/waveform")
async def waveform(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    width: int = Form(default=1920),
    height: int = Form(default=320),
    color: str = Form(default="lime"),
) -> Response:
    eng = ENGINES.get("ffmpeg-render")
    if eng is None or not is_ffmpeg_render_engine(eng):
        raise HTTPException(
            status_code=404, detail="ffmpeg-render engine not configured",
        )
    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )
    try:
        png = await eng.waveform(
            raw, filename, width=width, height=height, color=color,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await write_output(
        png,
        media_type="image/png",
        filename="waveform.png",
        output_path=output_path,
        output_url=output_url,
        extra_json={"engine": "ffmpeg-render", "kind": "waveform"},
    )


# ── /v1/audio/visualize — animated MP4/WebM video ──────────────────────────


@app.post("/v1/audio/visualize")
async def visualize(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    mode: str = Form(default="spectrum"),
    width: int = Form(default=1280),
    height: int = Form(default=720),
    fps: int = Form(default=30),
    container: str = Form(default="mp4"),
) -> Response:
    eng = ENGINES.get("ffmpeg-render")
    if eng is None or not is_ffmpeg_render_engine(eng):
        raise HTTPException(
            status_code=404, detail="ffmpeg-render engine not configured",
        )
    if mode not in visualize_modes():
        raise HTTPException(
            status_code=400,
            detail=f"unknown visualize mode {mode!r}; supported: {visualize_modes()}",
        )
    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )
    try:
        video = await eng.visualize(
            raw, filename,
            mode=mode, width=width, height=height, fps=fps, container=container,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    media_type = "video/mp4" if container == "mp4" else "video/webm"
    return await write_output(
        video,
        media_type=media_type,
        filename=f"visualize.{container}",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "engine": "ffmpeg-render",
            "mode": mode,
            "container": container,
            "width": width,
            "height": height,
            "fps": fps,
        },
    )


# ── /v1/audio/fingerprint — Chromaprint via fpcalc ─────────────────────────


@app.post("/v1/audio/fingerprint")
async def fingerprint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    analyze_seconds: float = Form(default=120.0),
    return_raw: bool = Form(default=False),
) -> dict[str, Any]:
    eng = ENGINES.get("audio-fingerprint")
    if eng is None or not is_fingerprint_engine(eng):
        raise HTTPException(
            status_code=404, detail="audio-fingerprint engine not configured",
        )
    raw, filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )
    try:
        return await eng.compute(
            raw, filename,
            analyze_seconds=analyze_seconds, return_raw=return_raw,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── /v1/midi/inspect — SMF bytes → JSON structure ──────────────────────────


@app.post("/v1/midi/inspect")
async def midi_inspect(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
) -> dict[str, Any]:
    eng = ENGINES.get("midi-compose")
    if eng is None or not is_midi_inspect_engine(eng):
        raise HTTPException(
            status_code=404, detail="midi-compose engine not configured",
        )
    raw, _filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )
    try:
        return await eng.inspect(raw)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── /v1/midi/transform — quantize / transpose / re-tempo / channel filter ──


@app.post("/v1/midi/transform")
async def midi_transform(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    transpose_semitones: int = Form(default=0),
    quantize_grid_beats: float | None = Form(default=None),
    tempo_bpm: float | None = Form(default=None),
    keep_channels: str | None = Form(default=None),
    drop_channels: str | None = Form(default=None),
) -> Response:
    eng = ENGINES.get("midi-compose")
    if eng is None or not is_midi_transform_engine(eng):
        raise HTTPException(
            status_code=404, detail="midi-compose engine not configured",
        )

    def _parse_chan_list(raw_str: str | None) -> list[int] | None:
        if raw_str is None or not raw_str.strip():
            return None
        try:
            return [int(x.strip()) for x in raw_str.split(",") if x.strip()]
        except ValueError as exc:
            raise HTTPException(
                status_code=400, detail=f"invalid channel list {raw_str!r}: {exc}",
            ) from exc

    keep = _parse_chan_list(keep_channels)
    drop = _parse_chan_list(drop_channels)

    raw, _filename = await resolve_input(
        file=file, file_path=file_path, file_url=file_url,
    )
    try:
        out_bytes = await eng.transform(
            raw,
            transpose_semitones=transpose_semitones,
            quantize_grid_beats=quantize_grid_beats,
            tempo_bpm=tempo_bpm,
            keep_channels=keep,
            drop_channels=drop,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await write_output(
        out_bytes,
        media_type="audio/midi",
        filename="transformed.mid",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "engine": "midi-compose",
            "size": len(out_bytes),
            "transpose_semitones": transpose_semitones,
            "quantize_grid_beats": quantize_grid_beats,
            "tempo_bpm": tempo_bpm,
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
