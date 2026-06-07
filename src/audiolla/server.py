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
  POST   /v1/audio/restore/{engine}  remove reverb/echo/noise (UVR); aggressive=true for deecho hard mode
  POST   /v1/audio/noise-reduce/{engine} noise reduction — engine=noise-reduce (DSP) or uvr-denoise (ML)
  POST   /v1/audio/visualize/image/spectrogram  static PNG spectrogram
  POST   /v1/audio/visualize/image/waveform     static PNG waveform
  POST   /v1/audio/visualize/video/{mode}       animated video (spectrum/waves/cqt/…)
  POST   /v1/audio/separate/hpss     harmonic+percussive separation via librosa HPSS
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
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import unquote

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response

from . import config
from . import files as files_mod
from .audio import (
    SUPPORTED_OUTPUT_FORMATS,
    AudioConversionError,
    audio_info,
    beat_slice,
    chords_to_midi_bytes,
    clip_detect,
    concat_audio,
    content_type_for,
    conv_reverb,
    convert_audio,
    deess,
    eq_audio,
    fade_audio,
    loop_audio,
    loudness_curve,
    mid_side_decode,
    mid_side_encode,
    mix_audio,
    multi_stream_zip,
    multiband_compress,
    pan_audio,
    repair_audio,
    reverse_audio,
    sidechain_duck,
    speed_audio,
    split_audio_equal,
    stereo_field,
    stereo_width_audio,
    transient_shape,
    trim_audio,
)
from .jobs import JOB_QUEUE
from .auth import BearerAuthMiddleware
from .engines import (
    build_engines,
    is_analysis_engine,
    is_basic_pitch_engine,
    is_beats_engine,
    is_chord_detect_engine,
    is_deepfilter_engine,
    is_diarize_engine,
    is_drum_pattern_engine,
    is_ffmpeg_render_engine,
    is_humanize_engine,
    is_thumbnail_engine,
    is_fingerprint_engine,
    is_fx_engine,
    is_loop_point_engine,
    is_loudness_engine,
    is_mastering_engine,
    is_metadata_engine,
    is_melody_engine,
    is_midi_compose_engine,
    is_midi_inspect_engine,
    is_midi_render_engine,
    is_midi_transform_engine,
    is_onsets_engine,
    is_pitch_correct_engine,
    is_segments_engine,
    is_classify_engine,
    is_embed_engine,
    is_hpss_engine,
    is_noise_reduce_engine,
    is_separation_engine,
    is_silence_engine,
    is_stretch_engine,
    is_tag_engine,
    is_transform_engine,
    is_uvr_restore_engine,
    is_vad_engine,
)
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
from .presets import load_presets as _load_presets  # noqa: E402, PLC0415

PRESETS = _load_presets(config.PRESETS_DIR)


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
                    slug,
                    last,
                    ttl,
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
_job_sweeper_task: asyncio.Task[None] | None = None

# Forward-declared so _lifespan can drive `MCP_SERVER.session_manager.run()`.
# Assigned to the real FastMCP instance below, before the app starts.
MCP_SERVER: Any = None


async def _job_sweeper() -> None:
    while True:
        try:
            await asyncio.sleep(300.0)
            cleaned = await JOB_QUEUE.cleanup(config.JOB_TTL_SECONDS)
            if cleaned:
                log.info("job sweeper: cleaned %d expired jobs", cleaned)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            log.exception("job sweeper iteration failed")


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

    global _sweeper_task, _job_sweeper_task
    _sweeper_task = asyncio.create_task(_idle_sweeper(), name="audiolla-sweeper")
    _job_sweeper_task = asyncio.create_task(_job_sweeper(), name="audiolla-job-sweeper")
    try:
        # MCP's streamable HTTP transport needs its session manager running
        # for the lifetime of the app.
        async with MCP_SERVER.session_manager.run():
            yield
    finally:
        for task in (_sweeper_task, _job_sweeper_task):
            if task is not None:
                task.cancel()
                try:
                    await task
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
            "loaded": engine.loaded(),
            "idle_seconds": engine.last_used_secs_ago(),
        }
        data.append(info)
    return {"object": "list", "data": data}


# ── /v1/catalog — endpoint catalog grouped by category ──────────────────────


_CATALOG_GROUPS: list[tuple[str, str, list[tuple[str, str, str]]]] = [
    ("separation", "Stem separation + harmonic/percussive split", [
        ("POST", "/v1/audio/separate", "Demucs/MDX/BS-Roformer stem separation"),
        ("POST", "/v1/audio/separate/hpss", "Harmonic/percussive split via librosa HPSS"),
        ("POST", "/v1/audio/remix", "Separate + per-stem gain/mute + bounce"),
    ]),
    ("restoration", "Removing artefacts: reverb, echo, noise, clipping, hum", [
        ("POST", "/v1/audio/restore/{engine}", "UVR de-reverb / de-echo / de-noise"),
        ("POST", "/v1/audio/noise-reduce/{engine}", "DSP (noisereduce) or ML (uvr-denoise)"),
        ("POST", "/v1/audio/repair", "Declip + dehum (50/60 Hz notch)"),
        ("POST", "/v1/audio/clip-detect", "Detect digital clipping (JSON only)"),
        ("POST", "/v1/audio/enhance/{engine}", "DeepFilterNet neural enhancement"),
    ]),
    ("dynamics", "Compression, limiting, ducking, transient shaping", [
        ("POST", "/v1/audio/fx", "Pedalboard chain — Compressor/Limiter/NoiseGate/+"),
        ("POST", "/v1/audio/multiband-compress", "N-band compressor with LR4 crossovers"),
        ("POST", "/v1/audio/transient", "Attack/sustain dual-compressor shaper"),
        ("POST", "/v1/audio/sidechain-duck", "Ducking via ffmpeg sidechaincompress"),
        ("POST", "/v1/audio/deess", "Sibilance compression (split-band)"),
        ("POST", "/v1/audio/normalize", "LUFS target normalisation"),
    ]),
    ("eq-spatial", "EQ, panning, M/S, stereo width", [
        ("POST", "/v1/audio/eq", "Parametric EQ via ffmpeg equalizer"),
        ("POST", "/v1/audio/pan", "Stereo pan (-1 left, +1 right)"),
        ("POST", "/v1/audio/stereo-width", "M/S width adjust (0=mono, 1=stock, 3=wide)"),
        ("POST", "/v1/audio/mid-side", "Encode L/R to M/S or decode back"),
        ("POST", "/v1/audio/stereo-field", "Stereo correlation / width / balance report"),
    ]),
    ("mastering", "Reference-matching + chain-preset mastering", [
        ("POST", "/v1/audio/master", "Matchering reference or pedalboard-chain preset"),
    ]),
    ("time-pitch", "Time-stretch, pitch shift, BPM/key matching", [
        ("POST", "/v1/audio/stretch", "Independent tempo factor + pitch semitones"),
        ("POST", "/v1/audio/speed", "Playback speed without pitch shift"),
        ("POST", "/v1/audio/bpm-match", "Detect BPM + stretch to target BPM"),
        ("POST", "/v1/audio/key-match", "Detect key + pitch-shift to target key"),
        ("POST", "/v1/audio/pitch-correct", "Snap to nearest semitone (auto-tune)"),
    ]),
    ("editing", "Trim, mix, concat, fade, reverse, loop, split", [
        ("POST", "/v1/audio/trim", "Cut to [start_sec, end_sec)"),
        ("POST", "/v1/audio/mix", "Mix multiple tracks with per-track gain"),
        ("POST", "/v1/audio/concat", "Concatenate N audio files"),
        ("POST", "/v1/audio/fade", "Fade in/out with selectable curve"),
        ("POST", "/v1/audio/reverse", "Reverse playback"),
        ("POST", "/v1/audio/loop", "Repeat N times"),
        ("POST", "/v1/audio/split", "Split into N equal or silence-detected parts"),
        ("POST", "/v1/audio/beat-slice", "Slice at detected beat positions"),
        ("POST", "/v1/audio/thumbnail", "Extract most-energetic N-sec segment"),
    ]),
    ("analysis", "Measurement + detection — JSON output", [
        ("POST", "/v1/audio/info", "ffprobe metadata"),
        ("POST", "/v1/audio/analyze", "BPM, key, loudness, duration, spectral"),
        ("POST", "/v1/audio/loudness", "Integrated LUFS measurement"),
        ("POST", "/v1/audio/loudness/curve", "Time-series RMS loudness envelope"),
        ("POST", "/v1/audio/beats", "Tempo + beat positions + optional click track"),
        ("POST", "/v1/audio/onsets", "Note-attack timestamps"),
        ("POST", "/v1/audio/melody", "F0 contour + optional MIDI quantize"),
        ("POST", "/v1/audio/segments", "Structural segmentation (verse/chorus)"),
        ("POST", "/v1/audio/chords", "Chord progression + key"),
        ("POST", "/v1/audio/silence", "Silent ranges + optional trim"),
        ("POST", "/v1/audio/fingerprint", "Chromaprint acoustic fingerprint"),
        ("POST", "/v1/audio/tag", "AudioSet zero-shot top-K labels"),
        ("POST", "/v1/audio/embed", "CLAP 512-dim semantic embedding"),
        ("POST", "/v1/audio/similar", "Cosine similarity between two clips"),
        ("POST", "/v1/audio/classify", "Zero-shot label-list classification"),
        ("POST", "/v1/audio/dj-prep", "BPM + key + LUFS + Camelot in one call"),
        ("POST", "/v1/audio/loop-point", "Find best seamless loop boundary"),
    ]),
    ("effects-creative", "Reverb (convolution), EFX", [
        ("POST", "/v1/audio/conv-reverb", "Apply user-supplied impulse response"),
    ]),
    ("visualize", "PNG spectrogram/waveform + animated video", [
        ("POST", "/v1/audio/visualize/image/spectrogram", "Static spectrogram PNG"),
        ("POST", "/v1/audio/visualize/image/waveform", "Static waveform PNG"),
        ("POST", "/v1/audio/visualize/video/{mode}", "Animated MP4/WebM (8 modes)"),
    ]),
    ("midi", "Compose / inspect / transform / render / drum / chords-to-MIDI", [
        ("POST", "/v1/midi/compose", "JSON spec → MIDI file"),
        ("POST", "/v1/midi/inspect", "MIDI → JSON structure"),
        ("POST", "/v1/midi/transform", "Quantize/transpose/re-tempo/channel filter"),
        ("POST", "/v1/midi/render", "MIDI → audio via fluidsynth"),
        ("POST", "/v1/midi/quantize", "Snap to rhythmic grid"),
        ("POST", "/v1/midi/humanize", "Add timing/velocity jitter"),
        ("POST", "/v1/midi/drum", "Step-sequencer spec → GM drum MIDI"),
        ("POST", "/v1/audio/to_midi/{engine}", "Polyphonic audio → MIDI via basic-pitch"),
        ("POST", "/v1/audio/chords-to-midi", "Chord detection → MIDI progression"),
    ]),
    ("metadata", "Read / write ID3, Vorbis, FLAC tags", [
        ("POST", "/v1/audio/metadata", "Read or write tags via mutagen"),
    ]),
    ("workflow", "Curated multi-step pipelines + ad-hoc chaining", [
        ("GET",  "/v1/presets", "List server-side curated workflows"),
        ("GET",  "/v1/presets/{name}", "Describe a single preset"),
        ("POST", "/v1/presets/{name}", "Run a curated preset against a file"),
        ("POST", "/v1/pipeline", "Run an ad-hoc {op, params} chain server-side"),
        ("GET",  "/v1/ops", "List available pipeline op slugs + their params"),
        ("POST", "/v1/audio/batch", "Multiple ops, one HTTP request"),
    ]),
    ("speech", "VAD, diarization", [
        ("POST", "/v1/audio/vad", "Voice activity detection (silero-vad)"),
        ("POST", "/v1/audio/diarize", "Speaker diarization (pyannote)"),
    ]),
    ("files", "Server-side file staging", [
        ("GET",    "/v1/files", "List staged files"),
        ("PUT",    "/v1/files/{path}", "Stage a file"),
        ("GET",    "/v1/files/{path}", "Retrieve a staged file"),
        ("DELETE", "/v1/files/{path}", "Delete a staged file"),
    ]),
    ("jobs", "Async job control", [
        ("GET",    "/v1/jobs", "List jobs (optional status filter)"),
        ("GET",    "/v1/jobs/{id}", "Poll one job"),
        ("DELETE", "/v1/jobs/{id}", "Cancel a job"),
    ]),
    ("management", "Engine discovery + lifecycle", [
        ("GET",    "/v1/engines", "List configured engines + load status"),
        ("GET",    "/v1/catalog", "This endpoint — full API catalog"),
        ("GET",    "/v1/ps", "List currently-loaded engines"),
        ("DELETE", "/v1/ps/{engine}", "Unload one engine (free RAM)"),
        ("POST",   "/v1/unload", "Unload all engines"),
        ("GET",    "/healthz", "Health check"),
    ]),
]


@app.get("/v1/catalog")
def catalog() -> dict[str, Any]:
    """Machine-readable catalog of every endpoint grouped by category. Use
    `/v1/engines` for the engine list, `/v1/presets` for curated workflows,
    `/v1/ops` for pipeline op slugs."""
    return {
        "object": "catalog",
        "categories": [
            {
                "name": name,
                "description": desc,
                "endpoints": [
                    {"method": m, "path": p, "summary": s}
                    for m, p, s in entries
                ],
            }
            for name, desc, entries in _CATALOG_GROUPS
        ],
    }


# ── /v1/ops, /v1/presets, /v1/pipeline ─────────────────────────────────────


@app.get("/v1/ops")
def list_ops() -> dict[str, Any]:
    """Available pipeline op slugs. Each op accepts ``(raw, filename, **params)``
    and returns audio bytes. Use these in `/v1/pipeline` or in preset YAML.
    Params are not enumerated here — see the corresponding `/v1/audio/{op}`
    REST endpoint's docs for the param schema (the op accepts the same
    keyword arguments)."""
    from .pipeline import available_ops as _available_ops  # noqa: PLC0415
    return {"object": "list", "data": _available_ops()}


@app.get("/v1/presets")
def list_presets() -> dict[str, Any]:
    """List server-side curated presets. Each entry has name + description.
    To see steps, GET `/v1/presets/{name}`. To run, POST to the same path."""
    return {
        "object": "list",
        "data": [
            {"name": p.name, "description": p.description}
            for p in PRESETS.values()
        ],
    }


@app.get("/v1/presets/{name}")
def describe_preset(name: str) -> dict[str, Any]:
    """Describe one preset including its full pipeline steps. Useful for
    auditing what a curated workflow does before running it."""
    preset = PRESETS.get(name)
    if preset is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown preset {name!r}; configured: {sorted(PRESETS)}",
        )
    return preset.to_dict()


@app.post("/v1/presets/{name}")
async def run_preset(
    name: str,
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Run a curated preset pipeline against an input file. The preset's
    steps are executed in order; intermediate audio stays in memory between
    steps. Returns the final audio (or routes to output_path / output_url
    same as any audio-producing endpoint)."""
    from .pipeline import PipelineError, run_pipeline  # noqa: PLC0415

    preset = PRESETS.get(name)
    if preset is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown preset {name!r}; configured: {sorted(PRESETS)}",
        )
    _validate_output_format(output_format)
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    # extra_json must be the SAME dict instance write_output reads later;
    # mutate steps in place so the response surfaces the actual log instead
    # of the empty seed list. (nonlocal reassign won't help — the helper has
    # already captured the dict by reference.)
    step_log: list[dict] = []
    extra_json: dict[str, Any] = {"preset": name, "steps": step_log}

    async def _produce() -> bytes:
        try:
            payload, log = await run_pipeline(ENGINES, raw, filename, preset.steps)
        except PipelineError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        step_log.extend(log)
        return payload

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"{name}.{output_format}",
        job_ext=output_format,
        endpoint=f"/v1/presets/{name}",
        output_path=output_path,
        output_url=output_url,
        extra_json=extra_json,
        async_job=async_job,
        webhook_url=webhook_url,
    )


@app.post("/v1/pipeline")
async def run_pipeline_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    output_format: str = Form(default="wav"),
    steps: str = Form(...),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Run an ad-hoc pipeline of ops against an input file. `steps` is a
    JSON array: `[{"op": "<slug>", "params": {...}}, ...]`. See `/v1/ops`
    for available op slugs. Each step's output feeds the next step's input.
    Server-side chaining — no intermediate HTTP roundtrips."""
    from .pipeline import PipelineError, run_pipeline  # noqa: PLC0415

    _validate_output_format(output_format)
    try:
        parsed_steps = json.loads(steps)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid steps JSON: {exc}") from exc
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    step_log: list[dict] = []
    extra_json: dict[str, Any] = {"steps": step_log}

    async def _produce() -> bytes:
        try:
            payload, log = await run_pipeline(ENGINES, raw, filename, parsed_steps)
        except PipelineError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        step_log.extend(log)
        return payload

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"pipeline.{output_format}",
        job_ext=output_format,
        endpoint="/v1/pipeline",
        output_path=output_path,
        output_url=output_url,
        extra_json=extra_json,
        async_job=async_job,
        webhook_url=webhook_url,
    )


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
            detail=(f"target_lufs must be in [-70.0, -0.1], got {target_lufs}"),
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


def _require_engine(pred, description: str) -> Any:
    for engine in ENGINES.values():
        if pred(engine):
            return engine
    raise HTTPException(status_code=503, detail=f"{description} engine not configured")


async def _submit_job(
    coro,
    *,
    endpoint: str,
    webhook_url: str | None,
    job_id: str,
) -> JSONResponse:
    async def _wrap():
        resp = await coro
        if isinstance(resp, JSONResponse):
            return json.loads(resp.body)
        return {"size": len(resp.body) if hasattr(resp, "body") else 0}

    await JOB_QUEUE.submit(
        _wrap, job_id=job_id, endpoint=endpoint, webhook_url=webhook_url
    )
    return JSONResponse({"job_id": job_id, "status": "pending"}, status_code=202)


async def _run_with_optional_job(
    produce: Callable[[], Awaitable[bytes]],
    *,
    media_type: str,
    filename: str,
    job_ext: str,
    endpoint: str,
    output_path: str | None,
    output_url: str | None,
    extra_json: dict | None,
    async_job: bool,
    webhook_url: str | None,
    extra_inline_headers: dict[str, str] | None = None,
) -> Response:
    """Standard pattern: invoke `produce()` to get bytes, then route the
    result through write_output. If `async_job` is True, the work runs in
    the background and the call returns a 202 with job_id.

    `produce` must be an async callable that returns bytes (the encoded
    audio/image/zip payload). AudioConversionError → HTTP 400. Other
    exceptions propagate so the caller / job queue can surface them.

    `job_ext` is the extension used for the auto-generated jobs/{id}.{ext}
    fallback when output_path is None and output_url is None.

    `extra_json` and `extra_inline_headers` are passed through to
    write_output. Callers that need to populate them based on values only
    available AFTER produce() runs can pass a mutable dict and mutate it
    inside produce() — it's the same instance write_output reads from."""
    if async_job:
        job_id = JOB_QUEUE.new_id()
        eff_path = output_path or (None if output_url else f"jobs/{job_id}.{job_ext}")

        async def _coro():
            try:
                payload = await produce()
            except AudioConversionError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            return await write_output(
                payload,
                media_type=media_type,
                filename=filename,
                output_path=eff_path,
                output_url=output_url,
                extra_json=extra_json,
                extra_inline_headers=extra_inline_headers,
            )

        return await _submit_job(
            _coro(), endpoint=endpoint, webhook_url=webhook_url, job_id=job_id,
        )

    try:
        payload = await produce()
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await write_output(
        payload,
        media_type=media_type,
        filename=filename,
        output_path=output_path,
        output_url=output_url,
        extra_json=extra_json,
        extra_inline_headers=extra_inline_headers,
    )


async def _run_json_or_audio(
    produce_json: Callable[[], Awaitable[dict[str, Any]]],
    *,
    extract_audio_b64_key: str,
    audio_media_type: str,
    audio_filename: str,
    job_ext: str,
    endpoint: str,
    write_audio: bool,
    output_path: str | None,
    output_url: str | None,
    async_job: bool,
    webhook_url: str | None,
) -> Any:
    """Used by beats/melody/silence: the engine returns a result dict that
    may include a base64-encoded audio payload. When `write_audio` is True
    and there's somewhere to write it, the audio is decoded and routed
    through write_output (the rest of the dict becomes extra_json).
    Otherwise the dict is returned as-is."""
    import base64 as _b64  # noqa: PLC0415

    async def _do() -> tuple[bytes | None, dict[str, Any]]:
        try:
            result = await produce_json()
        except AudioConversionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if write_audio and (output_path or output_url):
            audio = _b64.b64decode(result.pop(extract_audio_b64_key))
            return audio, result
        return None, result

    if async_job:
        job_id = JOB_QUEUE.new_id()
        eff_path = output_path or (None if output_url else f"jobs/{job_id}.{job_ext}")

        async def _coro():
            audio, rest = await _do()
            if audio is None:
                return rest
            return await write_output(
                audio,
                media_type=audio_media_type,
                filename=audio_filename,
                output_path=eff_path,
                output_url=output_url,
                extra_json=rest,
            )

        return await _submit_job(
            _coro(), endpoint=endpoint, webhook_url=webhook_url, job_id=job_id,
        )

    audio, rest = await _do()
    if audio is None:
        return rest
    return await write_output(
        audio,
        media_type=audio_media_type,
        filename=audio_filename,
        output_path=output_path,
        output_url=output_url,
        extra_json=rest,
    )


async def _evict_siblings(current_slug: str) -> None:
    siblings = [
        (slug, e) for slug, e in ENGINES.items() if slug != current_slug and e.loaded()
    ]
    if not siblings:
        return
    log.info(
        "evicting %d sibling engine(s) before loading %s: %s",
        len(siblings),
        current_slug,
        [slug for slug, _ in siblings],
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
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Stem separation. Supports Demucs engines (htdemucs, htdemucs_ft,
    htdemucs_6s, mdx_extra) and UVR separation engines (uvr-vocal-bsr,
    uvr-karaoke). The ``stems`` parameter filters which stems to return;
    omit to get all available stems for the engine.
    """
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
        file=file,
        file_path=file_path,
        file_url=file_url,
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

    # Two-pronged output: single requested stem → audio bytes; multiple →
    # ZIP. Precompute media_type/filename/job_ext from `requested` (known
    # before separation runs); extra_json gets mutated inside _produce()
    # for the multi-stem case to surface the actual stems returned.
    single_stem = len(requested) == 1
    if single_stem:
        sn = requested[0]
        media_type = content_type_for(output_format)
        out_filename = f"{sn}.{output_format}"
        job_ext = output_format
        extra_json: dict[str, Any] = {
            "engine": engine, "stem": sn, "output_format": output_format,
        }
    else:
        media_type = "application/zip"
        out_filename = f"{engine}-stems.zip"
        job_ext = "zip"
        extra_json = {"engine": engine, "output_format": output_format}

    async def _produce() -> bytes:
        await _evict_siblings(engine)
        stem_results = await eng.separate(
            raw, filename, stems=requested, output_format=output_format,
        )
        if single_stem:
            return stem_results[requested[0]]
        extra_json["stems"] = list(stem_results.keys())
        return multi_stream_zip(stem_results, output_format)

    return await _run_with_optional_job(
        _produce,
        media_type=media_type,
        filename=out_filename,
        job_ext=job_ext,
        endpoint="/v1/audio/separate",
        output_path=output_path,
        output_url=output_url,
        extra_json=extra_json,
        async_job=async_job,
        webhook_url=webhook_url,
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
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    _validate_output_format(output_format)

    if mode not in ("reference", "chain"):
        raise HTTPException(
            status_code=400, detail="mode must be 'reference' or 'chain'"
        )
    if mode == "chain" and not preset:
        raise HTTPException(status_code=400, detail="mode=chain requires a preset name")
    _validate_target_lufs(target_lufs)

    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )

    ref_raw: bytes | None = None
    ref_filename: str | None = None
    if mode == "reference":
        ref_raw, ref_filename = await resolve_input(
            file=reference,
            file_path=reference_path,
            file_url=reference_url,
            field_prefix="reference",
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
    else:
        engine_slug = "pedalboard-chain"
        eng = ENGINES.get(engine_slug)
        if eng is None:
            raise HTTPException(
                status_code=404, detail="pedalboard-chain engine not configured"
            )
        if not is_mastering_engine(eng):
            raise HTTPException(
                status_code=400,
                detail="pedalboard-chain engine does not support mastering",
            )
        available_presets = REGISTRY[engine_slug].get("presets", [])
        if preset not in available_presets:
            raise HTTPException(
                status_code=400,
                detail=f"unknown preset {preset!r}; available: {available_presets}",
            )

    async def _produce() -> bytes:
        await _evict_siblings(engine_slug)
        if mode == "reference":
            return await eng.master_reference(
                raw, filename, ref_raw, ref_filename,
                target_lufs=target_lufs, output_format=output_format,
            )
        return await eng.master_chain(
            raw, filename, preset=preset,
            target_lufs=target_lufs, output_format=output_format,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"mastered.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/master",
        output_path=output_path,
        output_url=output_url,
        extra_json={"engine": engine_slug, "mode": mode, "output_format": output_format},
        async_job=async_job,
        webhook_url=webhook_url,
    )


@app.post("/v1/audio/analyze", response_model=AnalyzeResult)
async def analyze(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    features: list[str] = Form(default=[]),
) -> AnalyzeResult:
    _VALID_FEATURES = frozenset(
        {"bpm", "key", "loudness", "duration", "spectral_centroid", "rms", "zcr"}
    )
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
        file=file,
        file_path=file_path,
        file_url=file_url,
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
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
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

    _VALID_OPS = frozenset(
        {
            "gain",
            "equalizer",
            "compand",
            "reverb",
            "pitch",
            "tempo",
            "rate",
            "channels",
            "trim",
            "pad",
        }
    )
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
        file=file,
        file_path=file_path,
        file_url=file_url,
    )

    async def _produce() -> bytes:
        return await eng.transform(
            raw, filename, operations=ops, output_format=output_format,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"transformed.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/transform",
        output_path=output_path,
        output_url=output_url,
        extra_json={"engine": engine_slug, "operations": ops, "output_format": output_format},
        async_job=async_job,
        webhook_url=webhook_url,
    )


@app.post("/v1/audio/loudness")
async def loudness(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
) -> LoudnessResult:
    """Measure integrated LUFS (ITU-R BS.1770-4) via pyloudnorm. Returns JSON only.
    To normalize to a target level use POST /v1/audio/normalize."""
    eng = ENGINES.get("librosa-analyze")
    if eng is None or not is_loudness_engine(eng):
        raise HTTPException(status_code=404, detail="librosa-analyze engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        lufs = await eng.measure_lufs(raw, filename)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return LoudnessResult(loudness_lufs=lufs, target_lufs=None, normalized=False)


@app.post("/v1/audio/normalize")
async def normalize(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    target_lufs: float = Form(...),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Any:
    """Normalize audio to a target LUFS level via pyloudnorm (gain scaling).
    Common targets: -14 (Spotify/YouTube), -16 (Apple Music), -23 (broadcast EBU R128)."""
    _validate_output_format(output_format)
    _validate_target_lufs(target_lufs)
    eng = ENGINES.get("librosa-analyze")
    if eng is None or not is_loudness_engine(eng):
        raise HTTPException(status_code=404, detail="librosa-analyze engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    extra_json: dict[str, Any] = {
        "target_lufs": target_lufs, "output_format": output_format,
    }
    inline_headers: dict[str, str] = {"X-Target-LUFS": str(target_lufs)}

    async def _produce() -> bytes:
        audio_bytes, lufs = await eng.normalize_lufs(
            raw, filename, target_lufs=target_lufs, output_format=output_format,
        )
        extra_json["measured_lufs"] = lufs
        inline_headers["X-Loudness-LUFS"] = str(lufs)
        return audio_bytes

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"normalized.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/normalize",
        output_path=output_path,
        output_url=output_url,
        extra_json=extra_json,
        extra_inline_headers=inline_headers,
        async_job=async_job,
        webhook_url=webhook_url,
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
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    _validate_output_format(output_format)

    try:
        chain = json.loads(effects)
        if not isinstance(chain, list):
            raise ValueError("effects must be a JSON array")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"invalid effects JSON: {exc}",
        ) from exc

    engine_slug = "fx-chain"
    eng = ENGINES.get(engine_slug)
    if eng is None:
        raise HTTPException(
            status_code=404,
            detail="fx-chain engine not configured",
        )
    if not is_fx_engine(eng):
        raise HTTPException(
            status_code=400,
            detail="fx-chain engine does not support fx",
        )

    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )

    async def _produce() -> bytes:
        return await eng.fx(raw, filename, effects=chain, output_format=output_format)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"fx.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/fx",
        output_path=output_path,
        output_url=output_url,
        extra_json={"engine": engine_slug, "effects": chain, "output_format": output_format},
        async_job=async_job,
        webhook_url=webhook_url,
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
                status_code=400,
                detail=f"invalid JSON body: {exc}",
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
                status_code=400,
                detail=f"invalid `spec` JSON: {exc}",
            ) from exc
        output_path = form.get("output_path") or output_path or None
        output_url = form.get("output_url") or output_url or None
        if output_path is not None:
            output_path = str(output_path) or None
        if output_url is not None:
            output_url = str(output_url) or None

    engine_slug = "midi-compose"
    eng = ENGINES.get(engine_slug)
    if eng is None:
        raise HTTPException(
            status_code=404,
            detail="midi-compose engine not configured",
        )
    if not is_midi_compose_engine(eng):
        raise HTTPException(
            status_code=400,
            detail="midi-compose engine missing compose()",
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
            status_code=404,
            detail="midi-render engine not configured",
        )
    if not is_midi_render_engine(eng):
        raise HTTPException(
            status_code=400,
            detail="midi-render engine missing render()",
        )

    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )

    try:
        audio_bytes = await eng.render(
            raw,
            filename,
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
                status_code=400,
                detail=f"invalid JSON body: {exc}",
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
                    status_code=400,
                    detail=f"gain must be a number: {q['gain']!r}",
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
                status_code=400,
                detail=f"invalid `spec` JSON: {exc}",
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
            midi_bytes,
            "composed.mid",
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
    start_bpm: float | None = Form(default=None),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Any:
    """Returns JSON with tempo + beat positions. With ``click_track=true``
    also synthesises a metronome-mixed audio render and includes a
    base64-encoded copy in the JSON.
    """
    _validate_output_format(output_format)
    eng = ENGINES.get("librosa-analyze")
    if eng is None or not is_beats_engine(eng):
        raise HTTPException(
            status_code=404,
            detail="librosa-analyze engine not configured",
        )
    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )

    async def _produce_json() -> dict[str, Any]:
        return await eng.beats(
            raw, filename,
            click_track=click_track, output_format=output_format, start_bpm=start_bpm,
        )

    return await _run_json_or_audio(
        _produce_json,
        extract_audio_b64_key="click_track_base64",
        audio_media_type=content_type_for(output_format),
        audio_filename=f"clicks.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/beats",
        write_audio=click_track,
        output_path=output_path,
        output_url=output_url,
        async_job=async_job,
        webhook_url=webhook_url,
    )


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
            status_code=404,
            detail="librosa-analyze engine not configured",
        )
    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
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
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Any:
    eng = ENGINES.get("librosa-analyze")
    if eng is None or not is_melody_engine(eng):
        raise HTTPException(
            status_code=404,
            detail="librosa-analyze engine not configured",
        )
    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )

    async def _produce_json() -> dict[str, Any]:
        result = await eng.melody(raw, filename, fmin=fmin, fmax=fmax, as_midi=as_midi)
        # midi_size is redundant with the encoded payload size; drop before
        # extra_json surfaces in the response. midi_base64 is the field the
        # helper extracts when as_midi+output_path/url are set.
        if as_midi and (output_path or output_url):
            result.pop("midi_size", None)
        return result

    return await _run_json_or_audio(
        _produce_json,
        extract_audio_b64_key="midi_base64",
        audio_media_type="audio/midi",
        audio_filename="melody.mid",
        job_ext="mid",
        endpoint="/v1/audio/melody",
        write_audio=as_midi,
        output_path=output_path,
        output_url=output_url,
        async_job=async_job,
        webhook_url=webhook_url,
    )


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
            status_code=404,
            detail="librosa-analyze engine not configured",
        )
    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
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
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Any:
    _validate_output_format(output_format)
    eng = ENGINES.get("silence-detect")
    if eng is None or not is_silence_engine(eng):
        raise HTTPException(
            status_code=404,
            detail="silence-detect engine not configured",
        )
    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )
    async def _produce_json() -> dict[str, Any]:
        return await eng.detect(
            raw, filename,
            threshold_db=threshold_db, min_duration_sec=min_duration_sec,
            trim_mode=trim_mode, output_format=output_format,
        )

    return await _run_json_or_audio(
        _produce_json,
        extract_audio_b64_key="trimmed_audio_base64",
        audio_media_type=content_type_for(output_format),
        audio_filename=f"trimmed.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/silence",
        write_audio=bool(trim_mode),
        output_path=output_path,
        output_url=output_url,
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/visualize/image/spectrogram  static PNG spectrogram ─────────────
# ── /v1/audio/visualize/image/waveform     static PNG waveform ─────────────────
# ── /v1/audio/visualize/video/{mode}       animated video ──────────────────────
# spectrogram → ffmpeg showspectrumpic → PNG (color + scale params)
# waveform    → ffmpeg showwavespic    → PNG (color param)
# spectrum|waves|cqt|freqs|volume|vectorscope|phasemeter|histogram → MP4/WebM


@app.post("/v1/audio/visualize/image/spectrogram")
async def visualize_spectrogram(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    width: int = Form(default=1280),
    height: int = Form(default=720),
    color: str = Form(default="intensity"),
    scale: str = Form(default="log"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    eng = ENGINES.get("ffmpeg-render")
    if eng is None or not is_ffmpeg_render_engine(eng):
        raise HTTPException(
            status_code=404,
            detail="ffmpeg-render engine not configured",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await eng.spectrogram(raw, filename, width=width, height=height, color=color, scale=scale)

    return await _run_with_optional_job(
        _produce,
        media_type="image/png",
        filename="spectrogram.png",
        job_ext="png",
        endpoint="/v1/audio/visualize/image/spectrogram",
        output_path=output_path,
        output_url=output_url,
        extra_json={"mode": "spectrogram"},
        async_job=async_job,
        webhook_url=webhook_url,
    )


@app.post("/v1/audio/visualize/image/waveform")
async def visualize_waveform(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    width: int = Form(default=1280),
    height: int = Form(default=720),
    color: str = Form(default="lime"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    eng = ENGINES.get("ffmpeg-render")
    if eng is None or not is_ffmpeg_render_engine(eng):
        raise HTTPException(
            status_code=404,
            detail="ffmpeg-render engine not configured",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await eng.waveform(raw, filename, width=width, height=height, color=color)

    return await _run_with_optional_job(
        _produce,
        media_type="image/png",
        filename="waveform.png",
        job_ext="png",
        endpoint="/v1/audio/visualize/image/waveform",
        output_path=output_path,
        output_url=output_url,
        extra_json={"mode": "waveform"},
        async_job=async_job,
        webhook_url=webhook_url,
    )


@app.post("/v1/audio/visualize/video/{mode}")
async def visualize_video(
    mode: str,
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    width: int = Form(default=1280),
    height: int = Form(default=720),
    fps: int = Form(default=30),
    container: str = Form(default="mp4"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    eng = ENGINES.get("ffmpeg-render")
    if eng is None or not is_ffmpeg_render_engine(eng):
        raise HTTPException(
            status_code=404,
            detail="ffmpeg-render engine not configured",
        )
    _all_modes = sorted(visualize_modes())
    if mode not in set(_all_modes):
        raise HTTPException(
            status_code=400,
            detail=f"unknown visualize mode {mode!r}; supported: {_all_modes}",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await eng.visualize(
            raw, filename, mode=mode, width=width, height=height, fps=fps, container=container,
        )

    media_type = "video/mp4" if container == "mp4" else "video/webm"
    return await _run_with_optional_job(
        _produce,
        media_type=media_type,
        filename=f"visualize.{container}",
        job_ext=container,
        endpoint=f"/v1/audio/visualize/video/{mode}",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "mode": mode,
            "container": container,
            "width": width,
            "height": height,
            "fps": fps,
        },
        async_job=async_job,
        webhook_url=webhook_url,
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
            status_code=404,
            detail="audio-fingerprint engine not configured",
        )
    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )
    try:
        return await eng.compute(
            raw,
            filename,
            analyze_seconds=analyze_seconds,
            return_raw=return_raw,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


# ── /v1/audio/restore/{engine} — UVR audio restoration ──────────────────────
# engine=uvr-dereverb  → BS-Roformer reverb removal
# engine=uvr-deecho    → VR Architecture echo removal (aggressive=true for hard mode)
# engine=uvr-denoise   → MelBand Roformer noise removal


@app.post("/v1/audio/restore/{engine}")
async def restore(
    engine: str,
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    output_format: str = Form(default="wav"),
    aggressive: bool = Form(default=False),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    _validate_output_format(output_format)
    eng = ENGINES.get(engine)
    if eng is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown engine {engine!r}; configured: {list(ENGINES.keys())}",
        )
    if not is_uvr_restore_engine(eng):
        raise HTTPException(
            status_code=400,
            detail=f"engine {engine!r} does not support restore operations",
        )
    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )

    async def _produce() -> bytes:
        return await eng.restore(raw, filename, output_format=output_format, aggressive=aggressive)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"restore.{output_format}",
        job_ext=output_format,
        endpoint=f"/v1/audio/restore/{engine}",
        output_path=output_path,
        output_url=output_url,
        extra_json={"engine": engine, "aggressive": aggressive, "output_format": output_format},
        async_job=async_job,
        webhook_url=webhook_url,
    )


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
            status_code=404,
            detail="midi-compose engine not configured",
        )
    raw, _filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
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
            status_code=404,
            detail="midi-compose engine not configured",
        )

    def _parse_chan_list(raw_str: str | None) -> list[int] | None:
        if raw_str is None or not raw_str.strip():
            return None
        try:
            return [int(x.strip()) for x in raw_str.split(",") if x.strip()]
        except ValueError as exc:
            raise HTTPException(
                status_code=400,
                detail=f"invalid channel list {raw_str!r}: {exc}",
            ) from exc

    keep = _parse_chan_list(keep_channels)
    drop = _parse_chan_list(drop_channels)

    raw, _filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
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


# ── /v1/audio/to_midi — polyphonic audio-to-MIDI via basic-pitch ────────────


@app.post("/v1/audio/to_midi/{engine}")
async def to_midi(
    engine: str,
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    onset_threshold: float = Form(default=0.5),
    frame_threshold: float = Form(default=0.3),
    minimum_note_length_ms: float = Form(default=58.0),
    minimum_frequency: float | None = Form(default=None),
    maximum_frequency: float | None = Form(default=None),
    multiple_pitch_bends: bool = Form(default=False),
    melodia_trick: bool = Form(default=True),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Convert audio to a polyphonic MIDI file via Spotify basic-pitch."""
    eng = ENGINES.get(engine)
    if eng is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown engine {engine!r}; configured: {list(ENGINES.keys())}",
        )
    if not is_basic_pitch_engine(eng):
        raise HTTPException(
            status_code=400,
            detail=f"engine {engine!r} does not support audio-to-MIDI transcription",
        )

    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )

    async def _produce() -> bytes:
        await _evict_siblings(engine)
        return await eng.to_midi(
            raw, filename,
            onset_threshold=onset_threshold, frame_threshold=frame_threshold,
            minimum_note_length_ms=minimum_note_length_ms,
            minimum_frequency=minimum_frequency, maximum_frequency=maximum_frequency,
            multiple_pitch_bends=multiple_pitch_bends, melodia_trick=melodia_trick,
        )

    # `size` is added automatically by write_output (len(payload)), so we
    # don't repeat it in extra_json — that was redundant in the prior code.
    return await _run_with_optional_job(
        _produce,
        media_type="audio/midi",
        filename="output.mid",
        job_ext="mid",
        endpoint=f"/v1/audio/to_midi/{engine}",
        output_path=output_path,
        output_url=output_url,
        extra_json={"engine": engine, "output_format": "mid"},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/enhance — neural speech/vocal enhancement (DeepFilterNet) ─────


@app.post("/v1/audio/enhance/{engine}")
async def audio_enhance(
    engine: str,
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Neural speech and vocal enhancement via DeepFilterNet DF3."""
    _validate_output_format(output_format)
    eng = ENGINES.get(engine)
    if eng is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown engine {engine!r}; configured: {list(ENGINES.keys())}",
        )
    if not is_deepfilter_engine(eng):
        raise HTTPException(
            status_code=400,
            detail=f"engine {engine!r} does not support neural enhancement",
        )

    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )

    async def _produce() -> bytes:
        await _evict_siblings(engine)
        return await eng.enhance(raw, filename, output_format=output_format)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"enhanced.{output_format}",
        job_ext=output_format,
        endpoint=f"/v1/audio/enhance/{engine}",
        output_path=output_path,
        output_url=output_url,
        extra_json={"engine": engine, "output_format": output_format},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/chords — chord + key detection via librosa ─────────────────────


@app.post("/v1/audio/chords")
async def chords(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    hop_length: int = Form(default=512),
    segment_min_duration_sec: float = Form(default=0.5),
) -> JSONResponse:
    eng = ENGINES.get("chord-detect")
    if eng is None:
        raise HTTPException(
            status_code=404,
            detail="chord-detect engine not configured",
        )
    if not is_chord_detect_engine(eng):
        raise HTTPException(
            status_code=400,
            detail="chord-detect engine does not support chord detection",
        )
    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )
    try:
        result = await eng.detect_chords(
            raw,
            filename,
            hop_length=hop_length,
            segment_min_duration_sec=segment_min_duration_sec,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/audio/vad — voice activity detection via silero-vad ──────────────────


@app.post("/v1/audio/vad")
async def vad(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    threshold: float = Form(default=0.5),
    min_speech_duration_ms: float = Form(default=250.0),
    min_silence_duration_ms: float = Form(default=100.0),
) -> JSONResponse:
    eng = ENGINES.get("silero-vad")
    if eng is None:
        raise HTTPException(
            status_code=404,
            detail="silero-vad engine not configured",
        )
    if not is_vad_engine(eng):
        raise HTTPException(
            status_code=400,
            detail="silero-vad engine does not support voice activity detection",
        )
    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )
    try:
        result = await eng.detect_voice(
            raw,
            filename,
            threshold=threshold,
            min_speech_duration_ms=min_speech_duration_ms,
            min_silence_duration_ms=min_silence_duration_ms,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/audio/diarize/{engine} — speaker diarization ─────────────────────────


@app.post("/v1/audio/diarize/{engine}")
async def diarize(
    engine: str,
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    num_speakers: int | None = Form(default=None),
    min_speakers: int | None = Form(default=None),
    max_speakers: int | None = Form(default=None),
) -> JSONResponse:
    eng = ENGINES.get(engine)
    if eng is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown engine {engine!r}; configured: {list(ENGINES.keys())}",
        )
    if not is_diarize_engine(eng):
        raise HTTPException(
            status_code=400,
            detail=f"engine {engine!r} does not support speaker diarization",
        )
    raw, filename = await resolve_input(
        file=file,
        file_path=file_path,
        file_url=file_url,
    )
    try:
        result = await eng.diarize(
            raw,
            filename,
            num_speakers=num_speakers,
            min_speakers=min_speakers,
            max_speakers=max_speakers,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/audio/stretch — time-stretch + pitch-shift ───────────────────────────


@app.post("/v1/audio/stretch")
async def stretch(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    tempo_factor: float = Form(default=1.0),
    pitch_semitones: float = Form(default=0.0),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Independently control playback speed (tempo_factor) and key (pitch_semitones).
    tempo_factor=0.5 = half speed; pitch_semitones=12 = one octave up."""
    _validate_output_format(output_format)
    eng = ENGINES.get("stretch")
    if eng is None or not is_stretch_engine(eng):
        raise HTTPException(status_code=404, detail="stretch engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await eng.stretch(
            raw, filename,
            tempo_factor=tempo_factor, pitch_semitones=pitch_semitones,
            output_format=output_format,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"stretched.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/stretch",
        output_path=output_path,
        output_url=output_url,
        extra_json={"tempo_factor": tempo_factor, "pitch_semitones": pitch_semitones},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/tag — AudioSet tagging via AST ─────────────────────────────────


@app.post("/v1/audio/tag")
async def tag(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    top_k: int = Form(default=10),
) -> JSONResponse:
    """Top-K AudioSet label predictions via Audio Spectrogram Transformer.
    Requires model cache (set HF_HUB_OFFLINE=0 on first run to download)."""
    eng = ENGINES.get("ast-tag")
    if eng is None or not is_tag_engine(eng):
        raise HTTPException(status_code=404, detail="ast-tag engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        result = await eng.tag(raw, filename, top_k=top_k)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/audio/embed — CLAP audio embeddings ──────────────────────────────────


@app.post("/v1/audio/embed")
async def embed(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    query_text: str | None = Form(default=None),
) -> JSONResponse:
    """512-dim L2-normalised audio embedding via LAION CLAP. With query_text,
    also returns cosine similarity to the text description.
    Requires model cache (set HF_HUB_OFFLINE=0 on first run to download)."""
    eng = ENGINES.get("clap-embed")
    if eng is None or not is_embed_engine(eng):
        raise HTTPException(status_code=404, detail="clap-embed engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        result = await eng.embed(raw, filename, query_text=query_text)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/audio/separate/hpss — harmonic/percussive source separation ─────────


@app.post("/v1/audio/separate/hpss")
async def hpss(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    margin: float = Form(default=1.0),
    kernel_size: int = Form(default=31),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Harmonic/percussive source separation via librosa HPSS median filter.
    Returns a ZIP containing harmonic.<fmt> (tonal content) and
    percussive.<fmt> (transients/drums). margin > 1 sharpens the separation."""
    _validate_output_format(output_format)
    eng = ENGINES.get("hpss")
    if eng is None or not is_hpss_engine(eng):
        raise HTTPException(status_code=404, detail="hpss engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    stem_keys: list[str] = []

    async def _produce() -> bytes:
        stems = await eng.hpss(
            raw, filename, margin=margin, kernel_size=kernel_size, output_format=output_format,
        )
        stem_keys[:] = list(stems.keys())
        return multi_stream_zip(stems, output_format)

    # stem_keys is populated by _produce(); the helper passes the same list
    # reference into extra_json, so write_output sees the populated value.
    extra_json: dict[str, Any] = {"stems": stem_keys, "output_format": output_format}

    return await _run_with_optional_job(
        _produce,
        media_type="application/zip",
        filename="hpss-stems.zip",
        job_ext="zip",
        endpoint="/v1/audio/separate/hpss",
        output_path=output_path,
        output_url=output_url,
        extra_json=extra_json,
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/noise-reduce/{engine} — noise reduction (DSP or ML) ────────────
# engine=noise-reduce  → noisereduce DSP (stationary/prop_decrease params)
# engine=uvr-denoise   → UVR MelBand Roformer ML (no extra params)


@app.post("/v1/audio/noise-reduce/{engine}")
async def noise_reduce(
    engine: str,
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    stationary: bool = Form(default=False),
    prop_decrease: float = Form(default=1.0),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    _validate_output_format(output_format)
    eng = ENGINES.get(engine)
    if eng is None:
        raise HTTPException(
            status_code=404,
            detail=f"unknown engine {engine!r}; configured: {list(ENGINES.keys())}",
        )
    is_dsp = is_noise_reduce_engine(eng)
    is_ml = is_uvr_restore_engine(eng)
    if not is_dsp and not is_ml:
        raise HTTPException(
            status_code=400,
            detail=f"engine {engine!r} does not support noise reduction",
        )
    if is_dsp and not (0.0 <= prop_decrease <= 1.0):
        raise HTTPException(
            status_code=400,
            detail=f"prop_decrease must be in [0.0, 1.0], got {prop_decrease}",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _run() -> bytes:
        if is_dsp:
            return await eng.reduce(
                raw, filename,
                stationary=stationary,
                prop_decrease=prop_decrease,
                output_format=output_format,
            )
        return await eng.restore(raw, filename, output_format=output_format)

    def _extra() -> dict:
        if is_dsp:
            return {"engine": engine, "stationary": stationary, "prop_decrease": prop_decrease, "output_format": output_format}
        return {"engine": engine, "output_format": output_format}

    return await _run_with_optional_job(
        _run,
        media_type=content_type_for(output_format),
        filename=f"denoised.{output_format}",
        job_ext=output_format,
        endpoint=f"/v1/audio/noise-reduce/{engine}",
        output_path=output_path,
        output_url=output_url,
        extra_json=_extra(),
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/info — ffprobe metadata ────────────────────────────────────────


@app.post("/v1/audio/info")
async def audio_info_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
) -> JSONResponse:
    """Probe audio file: duration, sample_rate, channels, codec, bit_depth, format."""
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        result = await asyncio.to_thread(audio_info, raw, filename)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/audio/trim — cut to time range ───────────────────────────────────────


@app.post("/v1/audio/trim")
async def trim(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    start_sec: float = Form(default=0.0),
    end_sec: float = Form(...),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Cut audio to [start_sec, end_sec). end_sec required."""
    _validate_output_format(output_format)
    if start_sec < 0:
        raise HTTPException(status_code=400, detail="start_sec must be >= 0")
    if end_sec <= start_sec:
        raise HTTPException(status_code=400, detail="end_sec must be > start_sec")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(
            trim_audio, raw, filename, start_sec, end_sec, output_format,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"trimmed.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/trim",
        output_path=output_path,
        output_url=output_url,
        extra_json={"start_sec": start_sec, "end_sec": end_sec, "output_format": output_format},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/mix — multi-track mix ──────────────────────────────────────────


@app.post("/v1/audio/mix")
async def mix(
    tracks: str = Form(...),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Mix multiple staged/URL tracks with per-track gain.
    tracks is a JSON array: [{"file_path":"...", "gain_db": 0.0}, ...]
    Each entry has file_path OR file_url plus optional gain_db (default 0.0).
    Requires at least 2 tracks."""
    _validate_output_format(output_format)
    try:
        track_specs = json.loads(tracks)
        if not isinstance(track_specs, list) or len(track_specs) < 2:
            raise ValueError("tracks must be a JSON array with at least 2 entries")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid tracks JSON: {exc}") from exc

    mix_inputs: list[tuple[bytes, str, float]] = []
    for i, spec in enumerate(track_specs):
        if not isinstance(spec, dict):
            raise HTTPException(status_code=400, detail=f"track {i}: must be an object")
        fp = spec.get("file_path") or None
        fu = spec.get("file_url") or None
        try:
            gain_db = float(spec.get("gain_db", 0.0))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"track {i}: invalid gain_db") from exc
        try:
            raw, filename = await resolve_input(file=None, file_path=fp, file_url=fu)
        except HTTPException as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=f"track {i}: {exc.detail}"
            ) from exc
        mix_inputs.append((raw, filename, gain_db))

    async def _produce() -> bytes:
        return await asyncio.to_thread(mix_audio, mix_inputs, output_format)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"mixed.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/mix",
        output_path=output_path,
        output_url=output_url,
        extra_json={"track_count": len(mix_inputs), "output_format": output_format},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/concat — concatenate N audio files ─────────────────────────────


@app.post("/v1/audio/concat")
async def concat(
    files: str = Form(...),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Concatenate N audio files in order.
    files is a JSON array: [{"file_path": "..."}, {"file_url": "..."}, ...]
    Each entry has file_path OR file_url. Requires at least 2."""
    _validate_output_format(output_format)
    try:
        file_specs = json.loads(files)
        if not isinstance(file_specs, list) or len(file_specs) < 2:
            raise ValueError("files must be a JSON array with at least 2 entries")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid files JSON: {exc}") from exc

    concat_inputs: list[tuple[bytes, str]] = []
    for i, spec in enumerate(file_specs):
        if not isinstance(spec, dict):
            raise HTTPException(status_code=400, detail=f"file {i}: must be an object")
        fp = spec.get("file_path") or None
        fu = spec.get("file_url") or None
        try:
            raw, filename = await resolve_input(file=None, file_path=fp, file_url=fu)
        except HTTPException as exc:
            raise HTTPException(
                status_code=exc.status_code, detail=f"file {i}: {exc.detail}"
            ) from exc
        concat_inputs.append((raw, filename))

    async def _produce() -> bytes:
        return await asyncio.to_thread(concat_audio, concat_inputs, output_format)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"concat.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/concat",
        output_path=output_path,
        output_url=output_url,
        extra_json={"file_count": len(concat_inputs), "output_format": output_format},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/speed — change playback speed ───────────────────────────────────


@app.post("/v1/audio/speed")
async def speed(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    speed: float = Form(...),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Change playback speed without pitch shift via ffmpeg atempo.
    speed=0.5 halves speed; speed=2.0 doubles. Range: 0.1–10.0."""
    _validate_output_format(output_format)
    if not (0.1 <= speed <= 10.0):
        raise HTTPException(
            status_code=400,
            detail=f"speed must be in [0.1, 10.0], got {speed}",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce_speed() -> bytes:
        return await asyncio.to_thread(speed_audio, raw, filename, speed, output_format)

    return await _run_with_optional_job(
        _produce_speed,
        media_type=content_type_for(output_format),
        filename=f"speed.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/speed",
        output_path=output_path,
        output_url=output_url,
        extra_json={"speed": speed, "output_format": output_format},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/convert — re-encode audio ─────────────────────────────────────


@app.post("/v1/audio/convert")
async def convert(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    output_format: str = Form(default="wav"),
    sample_rate: int | None = Form(default=None),
    channels: int | None = Form(default=None),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Re-encode audio to a different format, sample rate, or channel count."""
    _validate_output_format(output_format)
    if sample_rate is not None and sample_rate <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"sample_rate must be > 0, got {sample_rate}",
        )
    if channels is not None and channels not in (1, 2):
        raise HTTPException(
            status_code=400,
            detail=f"channels must be 1 or 2, got {channels}",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(
            convert_audio, raw, filename, output_format, sample_rate, channels,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"converted.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/convert",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "output_format": output_format,
            "sample_rate": sample_rate,
            "channels": channels,
        },
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/similar — cosine similarity via CLAP ───────────────────────────


@app.post("/v1/audio/similar")
async def similar(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    reference_file: UploadFile | None = File(default=None),
    reference_file_path: str | None = Form(default=None),
    reference_file_url: str | None = Form(default=None),
) -> JSONResponse:
    """Cosine similarity between two audio files via CLAP embeddings."""
    eng = ENGINES.get("clap-embed")
    if eng is None or not is_embed_engine(eng):
        raise HTTPException(status_code=404, detail="clap-embed engine not configured")
    raw_a, name_a = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    raw_b, name_b = await resolve_input(
        file=reference_file,
        file_path=reference_file_path,
        file_url=reference_file_url,
        field_prefix="reference_file",
    )
    try:
        result = await eng.similar(raw_a, name_a, raw_b, name_b)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/midi/quantize — snap MIDI note timings to rhythmic grid ───────────────


@app.post("/v1/midi/quantize")
async def midi_quantize(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    grid_beats: float = Form(default=0.25),
) -> Response:
    """Snap MIDI note timings to the nearest rhythmic grid.
    grid_beats: grid size in beats (0.25=16th, 0.5=8th, 1.0=quarter).
    Wraps /v1/midi/transform with only quantize_grid_beats set."""
    if grid_beats <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"grid_beats must be > 0, got {grid_beats}",
        )
    eng = ENGINES.get("midi-compose")
    if eng is None or not is_midi_transform_engine(eng):
        raise HTTPException(
            status_code=404,
            detail="midi-compose engine not configured",
        )
    raw, _filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        out_bytes = await eng.transform(raw, quantize_grid_beats=grid_beats)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await write_output(
        out_bytes,
        media_type="audio/midi",
        filename="quantized.mid",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "engine": "midi-compose",
            "size": len(out_bytes),
            "grid_beats": grid_beats,
        },
    )


# ── /v1/audio/classify — zero-shot CLAP classification ───────────────────────


@app.post("/v1/audio/classify")
async def classify(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    labels: str = Form(...),
) -> JSONResponse:
    """Zero-shot audio classification via CLAP. labels is a JSON array of strings.
    Returns results sorted by descending similarity score.
    Example labels: ["jazz", "hip-hop", "classical"] or ["male voice", "female voice"].
    Requires clap-embed model cache."""
    try:
        label_list = json.loads(labels)
        if not isinstance(label_list, list) or len(label_list) < 1:
            raise ValueError("labels must be a non-empty JSON array of strings")
        if not all(isinstance(lb, str) for lb in label_list):
            raise ValueError("all labels must be strings")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid labels: {exc}") from exc

    eng = ENGINES.get("clap-embed")
    if eng is None or not is_classify_engine(eng):
        raise HTTPException(status_code=404, detail="clap-embed engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        result = await eng.classify(raw, filename, labels=label_list)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/audio/fade — fade-in / fade-out ──────────────────────────────────────


@app.post("/v1/audio/fade")
async def fade(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    fade_in: float = Form(default=0.0),
    fade_out: float = Form(default=0.0),
    curve: str = Form(default="tri"),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Apply fade-in and/or fade-out. curve options: tri, qsin, esin, hsin, log, ipar,
    qua, cub, squ, cbr, par, exp, lin. At least one of fade_in/fade_out must be > 0."""
    _validate_output_format(output_format)
    if fade_in <= 0.0 and fade_out <= 0.0:
        raise HTTPException(
            status_code=400,
            detail="at least one of fade_in or fade_out must be > 0",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(
            fade_audio, raw, filename, output_format,
            fade_in=fade_in, fade_out=fade_out, curve=curve,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"faded.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/fade",
        output_path=output_path,
        output_url=output_url,
        extra_json={"fade_in": fade_in, "fade_out": fade_out, "curve": curve},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/reverse — reverse playback ─────────────────────────────────────


@app.post("/v1/audio/reverse")
async def reverse(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Reverse audio playback direction via ffmpeg areverse."""
    _validate_output_format(output_format)
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(reverse_audio, raw, filename, output_format)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"reversed.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/reverse",
        output_path=output_path,
        output_url=output_url,
        extra_json=None,
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/loop — repeat audio ────────────────────────────────────────────


@app.post("/v1/audio/loop")
async def loop(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    count: int = Form(default=2),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Repeat audio count times (minimum 2). Uses ffmpeg aloop filter."""
    _validate_output_format(output_format)
    if count < 2:
        raise HTTPException(
            status_code=400,
            detail=f"count must be >= 2, got {count}",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(loop_audio, raw, filename, output_format, count)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"looped.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/loop",
        output_path=output_path,
        output_url=output_url,
        extra_json={"count": count},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/bpm-match — detect BPM + time-stretch to target ────────────────


@app.post("/v1/audio/bpm-match")
async def bpm_match(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    target_bpm: float = Form(...),
    pitch_semitones: float = Form(default=0.0),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Detect source BPM via librosa then time-stretch to target_bpm.
    Requires both librosa-analyze and stretch engines."""
    _validate_output_format(output_format)
    if target_bpm <= 0:
        raise HTTPException(
            status_code=400,
            detail=f"target_bpm must be > 0, got {target_bpm}",
        )
    librosa_eng = ENGINES.get("librosa-analyze")
    if librosa_eng is None or not is_beats_engine(librosa_eng):
        raise HTTPException(
            status_code=404,
            detail="librosa-analyze engine not configured",
        )
    stretch_eng = ENGINES.get("stretch")
    if stretch_eng is None or not is_stretch_engine(stretch_eng):
        raise HTTPException(
            status_code=404,
            detail="stretch engine not configured",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    # extra_json fields depend on detected source_bpm — populated by produce()
    meta: dict[str, Any] = {
        "target_bpm": target_bpm, "pitch_semitones": pitch_semitones,
    }

    async def _produce() -> bytes:
        beats_result = await librosa_eng.beats(raw, filename)
        source_bpm = beats_result["tempo_bpm"]
        if not source_bpm:
            raise HTTPException(
                status_code=400, detail="could not detect source BPM from audio",
            )
        tempo_factor = target_bpm / source_bpm
        meta["source_bpm"] = round(source_bpm, 2)
        meta["tempo_factor"] = round(tempo_factor, 4)
        return await stretch_eng.stretch(
            raw, filename,
            tempo_factor=tempo_factor, pitch_semitones=pitch_semitones,
            output_format=output_format,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"bpm_matched.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/bpm-match",
        output_path=output_path,
        output_url=output_url,
        extra_json=meta,
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/stereo-width — M/S stereo width ────────────────────────────────


@app.post("/v1/audio/stereo-width")
async def stereo_width(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    width: float = Form(default=1.0),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Adjust stereo width via M/S processing. width=0.0 → mono, 1.0 → original,
    >1.0 → wider. Range: [0.0, 3.0]."""
    _validate_output_format(output_format)
    if not (0.0 <= width <= 3.0):
        raise HTTPException(
            status_code=400,
            detail=f"width must be in [0.0, 3.0], got {width}",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(stereo_width_audio, raw, filename, output_format, width)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"stereo_width.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/stereo-width",
        output_path=output_path,
        output_url=output_url,
        extra_json={"width": width},
        async_job=async_job,
        webhook_url=webhook_url,
    )


_NOTE_TO_SEMITONE: dict[str, int] = {
    "C": 0, "C#": 1, "DB": 1, "D": 2, "D#": 3, "EB": 3,
    "E": 4, "F": 5, "F#": 6, "GB": 6, "G": 7, "G#": 8,
    "AB": 8, "A": 9, "A#": 10, "BB": 10, "B": 11,
}

_MODE_SUFFIXES = frozenset({
    "major", "minor", "maj", "min", "m",
})


def _parse_key_root(key_str: str) -> int:
    """Parse a key string like 'C', 'F#', 'Bb', 'D minor' to a semitone (0-11)."""
    parts = key_str.strip().upper().split()
    root = parts[0]
    # Strip mode suffix that may be attached without space (e.g. "Cm")
    for suffix in sorted(_MODE_SUFFIXES, key=len, reverse=True):
        upper = suffix.upper()
        if root.endswith(upper) and len(root) > len(upper):
            root = root[: -len(upper)]
            break
    semitone = _NOTE_TO_SEMITONE.get(root)
    if semitone is None:
        raise HTTPException(
            status_code=400,
            detail=f"unrecognised key root {root!r}; "
            f"valid roots: {list(_NOTE_TO_SEMITONE.keys())}",
        )
    return semitone


# ── /v1/audio/split — split into equal or silence-based segments ──────────────


@app.post("/v1/audio/split")
async def split(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    mode: str = Form(default="equal"),
    count: int | None = Form(default=None),
    threshold_db: float = Form(default=-30.0),
    min_duration_sec: float = Form(default=0.5),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Split audio into segments. mode=equal (requires count>=2) or mode=silence
    (uses threshold_db/min_duration_sec via silence-detect engine).
    Returns a ZIP of numbered segment files."""
    if mode not in ("equal", "silence"):
        raise HTTPException(status_code=400, detail="mode must be 'equal' or 'silence'")
    _validate_output_format(output_format)
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    if mode == "equal":
        if count is None or count < 2:
            raise HTTPException(
                status_code=400,
                detail="mode=equal requires count >= 2",
            )
        try:
            segments = await asyncio.to_thread(
                split_audio_equal, raw, filename, output_format, count
            )
        except AudioConversionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    else:
        eng = ENGINES.get("silence-detect")
        if eng is None or not is_silence_engine(eng):
            raise HTTPException(
                status_code=404,
                detail="silence-detect engine not configured",
            )
        try:
            result = await eng.detect(
                raw,
                filename,
                threshold_db=threshold_db,
                min_duration_sec=min_duration_sec,
            )
        except AudioConversionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        non_silent_ranges = result.get("non_silent_ranges", [])
        if not non_silent_ranges:
            raise HTTPException(status_code=400, detail="no non-silent segments found")
        segments = []
        for r in non_silent_ranges:
            try:
                seg = await asyncio.to_thread(
                    trim_audio, raw, filename,
                    r["start_sec"], r["end_sec"], output_format,
                )
            except AudioConversionError as exc:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            segments.append(seg)

    zip_dict = {f"segment_{i:03d}": seg for i, seg in enumerate(segments)}
    zip_bytes = multi_stream_zip(zip_dict, output_format)

    async def _produce() -> bytes:
        return zip_bytes  # split work is already done above

    return await _run_with_optional_job(
        _produce,
        media_type="application/zip",
        filename="split.zip",
        job_ext="zip",
        endpoint="/v1/audio/split",
        output_path=output_path,
        output_url=output_url,
        extra_json={"segments": len(segments), "mode": mode},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/pan — stereo pan ───────────────────────────────────────────────


@app.post("/v1/audio/pan")
async def pan(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    position: float = Form(default=0.0),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Pan audio in the stereo field. position: -1.0=hard left, 0.0=center, 1.0=hard right."""
    _validate_output_format(output_format)
    if not (-1.0 <= position <= 1.0):
        raise HTTPException(
            status_code=400,
            detail=f"position must be in [-1.0, 1.0], got {position}",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(pan_audio, raw, filename, output_format, position)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"panned.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/pan",
        output_path=output_path,
        output_url=output_url,
        extra_json={"position": position},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/eq — parametric EQ ─────────────────────────────────────────────


@app.post("/v1/audio/eq")
async def eq(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    bands: str = Form(...),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Parametric EQ via ffmpeg equalizer filter.
    bands is a JSON array: [{"freq": 1000, "gain_db": 3.0, "width_hz": 100}, ...]"""
    _validate_output_format(output_format)
    try:
        band_list = json.loads(bands)
        if not isinstance(band_list, list):
            raise ValueError("bands must be a JSON array")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"invalid bands JSON: {exc}",
        ) from exc
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(eq_audio, raw, filename, output_format, band_list)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"eq.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/eq",
        output_path=output_path,
        output_url=output_url,
        extra_json={"band_count": len(band_list)},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/key-match — detect key + pitch-shift to target ─────────────────


@app.post("/v1/audio/key-match")
async def key_match(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    target_key: str = Form(...),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Detect source key via chord-detect then pitch-shift to target_key.
    target_key: note name, e.g. C, F#, Bb, D#. Case-insensitive.
    Requires chord-detect and stretch engines."""
    _validate_output_format(output_format)
    target_semitone = _parse_key_root(target_key)
    chord_detect_eng = ENGINES.get("chord-detect")
    if chord_detect_eng is None or not is_chord_detect_engine(chord_detect_eng):
        raise HTTPException(
            status_code=404,
            detail="chord-detect engine not configured",
        )
    stretch_eng = ENGINES.get("stretch")
    if stretch_eng is None or not is_stretch_engine(stretch_eng):
        raise HTTPException(
            status_code=404,
            detail="stretch engine not configured",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    meta: dict[str, Any] = {"target_key": target_key.strip()}

    async def _produce() -> bytes:
        source_result = await chord_detect_eng.detect_chords(raw, filename)
        source_key = source_result["key"]
        source_semitone = _parse_key_root(source_key)
        diff = (target_semitone - source_semitone) % 12
        if diff > 6:
            diff -= 12
        meta["source_key"] = source_key
        meta["semitones"] = diff
        return await stretch_eng.stretch(
            raw, filename,
            tempo_factor=1.0, pitch_semitones=float(diff),
            output_format=output_format,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"key_matched.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/key-match",
        output_path=output_path,
        output_url=output_url,
        extra_json=meta,
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/sidechain-duck — sidechain compression / ducking ───────────────


@app.post("/v1/audio/sidechain-duck")
async def sidechain_duck_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    trigger_file: UploadFile | None = File(default=None),
    trigger_file_path: str | None = Form(default=None),
    trigger_file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    threshold_db: float = Form(default=-20.0),
    ratio: float = Form(default=4.0),
    attack_ms: float = Form(default=10.0),
    release_ms: float = Form(default=200.0),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Duck primary audio when trigger audio is loud (voiceover-over-music effect).
    threshold_db: trigger level. ratio: compression ratio. attack_ms/release_ms: timing."""
    _validate_output_format(output_format)
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    trigger_raw, trigger_filename = await resolve_input(
        file=trigger_file,
        file_path=trigger_file_path,
        file_url=trigger_file_url,
        field_prefix="trigger_file",
    )

    async def _produce() -> bytes:
        return await asyncio.to_thread(
            sidechain_duck,
            raw, filename, trigger_raw, trigger_filename,
            output_format, threshold_db, ratio, attack_ms, release_ms,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"ducked.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/sidechain-duck",
        output_path=output_path,
        output_url=output_url,
        extra_json={"threshold_db": threshold_db, "ratio": ratio},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/metadata — read/write audio file tags ─────────────────────────


@app.post("/v1/audio/metadata")
async def audio_metadata(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    tags: str | None = Form(default=None),
) -> JSONResponse:
    """Read or write audio file tags (ID3, Vorbis, FLAC) via mutagen.
    If tags is provided (JSON object), writes those tags and returns the updated
    tag set. Without tags, reads and returns all tags."""
    eng = ENGINES.get("metadata")
    if eng is None or not is_metadata_engine(eng):
        raise HTTPException(status_code=404, detail="metadata engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    write_tags: dict | None = None
    if tags is not None:
        try:
            write_tags = json.loads(tags)
            if not isinstance(write_tags, dict):
                raise ValueError("tags must be a JSON object")
        except (json.JSONDecodeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid tags JSON: {exc}") from exc

    try:
        if write_tags is not None:
            updated_bytes = await eng.write_tags(raw, filename, write_tags)
            updated_tags = await eng.read_tags(updated_bytes, filename)
            return JSONResponse(updated_tags)
        result = await eng.read_tags(raw, filename)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/audio/clip-detect — detect digital clipping ─────────────────────────


@app.post("/v1/audio/clip-detect")
async def clip_detect_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
) -> JSONResponse:
    """Detect digital clipping via numpy. Returns clipped, clip_count, clip_ratio,
    peak_db, duration_sec, sample_rate, channels."""
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        result = await asyncio.to_thread(clip_detect, raw, filename)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/audio/mid-side — M/S encode or decode ───────────────────────────────


@app.post("/v1/audio/mid-side")
async def mid_side(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    mode: str = Form(...),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Encode stereo to Mid/Side or decode M/S back to stereo.
    mode: 'encode' (L/R → M/S) or 'decode' (M/S → L/R)."""
    if mode not in ("encode", "decode"):
        raise HTTPException(status_code=400, detail="mode must be 'encode' or 'decode'")
    _validate_output_format(output_format)
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        if mode == "encode":
            return await asyncio.to_thread(mid_side_encode, raw, filename, output_format)
        return await asyncio.to_thread(mid_side_decode, raw, filename, output_format)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"mid_side_{mode}.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/mid-side",
        output_path=output_path,
        output_url=output_url,
        extra_json={"mode": mode},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/beat-slice — slice audio at beat timestamps ───────────────────


@app.post("/v1/audio/beat-slice")
async def beat_slice_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Slice audio at beat positions detected by librosa-analyze.
    Returns a ZIP of numbered beat slices. Requires librosa-analyze engine."""
    _validate_output_format(output_format)
    librosa_eng = ENGINES.get("librosa-analyze")
    if librosa_eng is None or not is_beats_engine(librosa_eng):
        raise HTTPException(status_code=404, detail="librosa-analyze engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    meta: dict[str, Any] = {"output_format": output_format}

    async def _produce() -> bytes:
        beats_result = await librosa_eng.beats(raw, filename)
        beat_times = beats_result.get("beats", [])
        if not beat_times:
            raise HTTPException(status_code=400, detail="no beats detected in audio")
        meta["beat_count"] = len(beat_times)
        return await asyncio.to_thread(beat_slice, raw, filename, beat_times, output_format)

    return await _run_with_optional_job(
        _produce,
        media_type="application/zip",
        filename="beat_slices.zip",
        job_ext="zip",
        endpoint="/v1/audio/beat-slice",
        output_path=output_path,
        output_url=output_url,
        extra_json=meta,
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/conv-reverb — convolution reverb ──────────────────────────────


@app.post("/v1/audio/conv-reverb")
async def conv_reverb_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    ir_file: UploadFile | None = File(default=None),
    ir_file_path: str | None = Form(default=None),
    ir_file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    wet_mix: float = Form(default=0.3),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Convolution reverb using an impulse response (IR) file.
    wet_mix: 0.0=dry only, 1.0=wet only. Range [0.0, 1.0]."""
    _validate_output_format(output_format)
    if not (0.0 <= wet_mix <= 1.0):
        raise HTTPException(
            status_code=400,
            detail=f"wet_mix must be in [0.0, 1.0], got {wet_mix}",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    ir_raw, ir_filename = await resolve_input(
        file=ir_file,
        file_path=ir_file_path,
        file_url=ir_file_url,
        field_prefix="ir_file",
    )

    async def _produce() -> bytes:
        return await asyncio.to_thread(
            conv_reverb, raw, filename, ir_raw, ir_filename,
            wet_mix=wet_mix, output_format=output_format,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"conv_reverb.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/conv-reverb",
        output_path=output_path,
        output_url=output_url,
        extra_json={"wet_mix": wet_mix},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/transient — transient shaper ──────────────────────────────────


@app.post("/v1/audio/transient")
async def transient_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    attack_gain_db: float = Form(default=0.0),
    sustain_gain_db: float = Form(default=0.0),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Transient shaper via dual-compressor attack/sustain blending.
    attack_gain_db: boost/cut transient attack (positive=punchier, negative=softer).
    sustain_gain_db: boost/cut sustain (positive=sustain boost, negative=sustain cut)."""
    _validate_output_format(output_format)
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(
            transient_shape, raw, filename,
            attack_gain_db=attack_gain_db,
            sustain_gain_db=sustain_gain_db,
            output_format=output_format,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"transient.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/transient",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "attack_gain_db": attack_gain_db,
            "sustain_gain_db": sustain_gain_db,
        },
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/multiband-compress — N-band compressor ─────────────────────────


@app.post("/v1/audio/multiband-compress")
async def multiband_compress_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    crossovers_hz: str = Form(...),
    bands: str = Form(...),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Multiband compression.

    crossovers_hz: JSON array of ascending crossover frequencies (Hz),
      e.g. "[200, 2000]" for a 3-band split (low/mid/high).
    bands: JSON array of compressor specs, one per band (len = len(crossovers_hz)+1).
      Each: {threshold_db, ratio, attack_ms?, release_ms?, makeup_db?}.

    Bands split with zero-phase LR4-equivalent filters; sum reconstructs
    when bypassed. Output is the summed compressed signal."""
    _validate_output_format(output_format)
    try:
        xo = json.loads(crossovers_hz)
        bds = json.loads(bands)
    except (json.JSONDecodeError, TypeError) as exc:
        raise HTTPException(
            status_code=400,
            detail=f"crossovers_hz and bands must be valid JSON: {exc}",
        ) from exc

    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(
            multiband_compress, raw, filename,
            crossovers_hz=xo, bands=bds,
            output_format=output_format,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"multiband.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/multiband-compress",
        output_path=output_path,
        output_url=output_url,
        extra_json={"crossovers_hz": xo, "bands": bds},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/remix — stem separation + per-stem mix ────────────────────────


@app.post("/v1/audio/remix")
async def remix(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    engine: str = Form(default="htdemucs"),
    stem_mix: str = Form(default="{}"),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Separate audio into stems then bounce back with per-stem gain/mute control.
    stem_mix is a JSON object: {"vocals": {"gain_db": -6}, "drums": {"mute": true}, ...}
    Missing stems use gain_db=0.0, mute=false. Requires a separation engine."""
    _validate_output_format(output_format)
    try:
        _parsed = json.loads(stem_mix)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"invalid stem_mix JSON: {exc}") from exc
    if not isinstance(_parsed, dict):
        raise HTTPException(status_code=400, detail="stem_mix must be a JSON object")
    stem_mix_spec: dict = _parsed

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
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    meta: dict[str, Any] = {"engine": engine}

    async def _produce() -> bytes:
        await _evict_siblings(engine)
        stems = await eng.separate(raw, filename, output_format=output_format)
        mix_inputs: list[tuple[bytes, str, float]] = []
        for stem_name, stem_bytes in stems.items():
            spec = stem_mix_spec.get(stem_name, {})
            if spec.get("mute", False):
                continue
            gain_db = float(spec.get("gain_db", 0.0))
            mix_inputs.append((stem_bytes, f"{stem_name}.{output_format}", gain_db))
        if not mix_inputs:
            raise HTTPException(status_code=400, detail="all stems are muted")
        meta["stems"] = list(stems.keys())
        return await asyncio.to_thread(mix_audio, mix_inputs, output_format)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"remix.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/remix",
        output_path=output_path,
        output_url=output_url,
        extra_json=meta,
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── Camelot wheel for DJ prep ─────────────────────────────────────────────────

_CAMELOT: dict[str, str] = {
    "C major": "8B", "A minor": "8A",
    "G major": "9B", "E minor": "9A",
    "D major": "10B", "B minor": "10A",
    "A major": "11B", "F# minor": "11A",
    "E major": "12B", "C# minor": "12A",
    "B major": "1B", "G# minor": "1A",
    "F# major": "2B", "D# minor": "2A",
    "C# major": "3B", "A# minor": "3A",
    "G# major": "4B", "F minor": "4A",
    "D# major": "5B", "C minor": "5A",
    "A# major": "6B", "G minor": "6A",
    "F major": "7B", "D minor": "7A",
}


# ── /v1/audio/dj-prep — BPM + key + LUFS + Camelot ─────────────────────────


@app.post("/v1/audio/dj-prep")
async def dj_prep(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
) -> JSONResponse:
    """DJ track analysis: BPM, key (+ Camelot wheel position), integrated LUFS.
    Requires librosa-analyze + chord-detect + pedalboard-chain or matchering engines."""
    librosa_eng = ENGINES.get("librosa-analyze")
    if librosa_eng is None or not is_beats_engine(librosa_eng):
        raise HTTPException(status_code=404, detail="librosa-analyze engine not configured")
    chord_eng = ENGINES.get("chord-detect")
    if chord_eng is None or not is_chord_detect_engine(chord_eng):
        raise HTTPException(status_code=404, detail="chord-detect engine not configured")
    loudness_eng = next(
        (e for e in ENGINES.values() if is_loudness_engine(e)), None
    )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        beats_result = await librosa_eng.beats(raw, filename)
        chord_result = await chord_eng.detect_chords(raw, filename)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    bpm = beats_result.get("tempo_bpm")
    key = chord_result.get("key", "")
    camelot = _CAMELOT.get(key, "")

    lufs: float | None = None
    if loudness_eng is not None:
        try:
            lufs = await loudness_eng.measure_lufs(raw, filename)
        except AudioConversionError:
            pass

    return JSONResponse({
        "bpm": round(bpm, 2) if bpm else None,
        "key": key,
        "camelot": camelot,
        "integrated_lufs": round(lufs, 2) if lufs is not None else None,
    })


# ── /v1/audio/loudness/curve — RMS envelope over time ────────────────────────


@app.post("/v1/audio/loudness/curve")
async def loudness_curve_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    hop_length: int = Form(default=512),
) -> JSONResponse:
    """Compute the RMS loudness envelope as a time series.
    Returns {curve: [{time_sec, rms_db}, ...], duration, sample_rate, points}."""
    if hop_length < 64 or hop_length > 8192:
        raise HTTPException(
            status_code=400,
            detail=f"hop_length must be in [64, 8192], got {hop_length}",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        result = await asyncio.to_thread(loudness_curve, raw, filename, hop_length=hop_length)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/audio/pitch-correct — auto-tune toward nearest semitone ──────────────


@app.post("/v1/audio/pitch-correct")
async def pitch_correct_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    strength: float = Form(default=1.0),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Pitch-correct audio toward the nearest chromatic semitone via pyin F0 detection.
    strength=1.0 is full correction, 0.0 is bypass. Requires librosa-analyze engine."""
    _validate_output_format(output_format)
    if not (0.0 <= strength <= 1.0):
        raise HTTPException(
            status_code=400,
            detail=f"strength must be in [0.0, 1.0], got {strength}",
        )
    eng = next((e for e in ENGINES.values() if is_pitch_correct_engine(e)), None)
    if eng is None:
        raise HTTPException(status_code=404, detail="pitch-correct engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await eng.pitch_correct(raw, filename, strength=strength, output_format=output_format)

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"pitch_correct.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/pitch-correct",
        output_path=output_path,
        output_url=output_url,
        extra_json={"strength": strength},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/repair — declip + dehum ────────────────────────────────────────


@app.post("/v1/audio/repair")
async def repair_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    declip: bool = Form(default=True),
    dehum: bool = Form(default=False),
    hum_freq: float = Form(default=50.0),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Repair audio: interpolate clipped samples and/or remove mains hum.
    declip: fix digital clipping. dehum: notch-filter 50/60 Hz hum.
    hum_freq: fundamental hum frequency (50 for EU, 60 for US)."""
    _validate_output_format(output_format)
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(
            repair_audio, raw, filename,
            declip=declip, dehum=dehum, hum_freq=hum_freq,
            output_format=output_format,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"repaired.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/repair",
        output_path=output_path,
        output_url=output_url,
        extra_json={"declip": declip, "dehum": dehum, "hum_freq": hum_freq},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/loop-point — find best seamless loop boundary ─────────────────


@app.post("/v1/audio/loop-point")
async def loop_point_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    min_loop_bars: int = Form(default=4),
    num_candidates: int = Form(default=5),
) -> JSONResponse:
    """Find the best seamless loop point in audio using beat-grid MFCC similarity.
    Returns loop_start_sec, loop_end_sec, bars, score, tempo_bpm, candidates."""
    if min_loop_bars < 1 or min_loop_bars > 64:
        raise HTTPException(
            status_code=400,
            detail=f"min_loop_bars must be in [1, 64], got {min_loop_bars}",
        )
    if num_candidates < 1 or num_candidates > 20:
        raise HTTPException(
            status_code=400,
            detail=f"num_candidates must be in [1, 20], got {num_candidates}",
        )
    eng = next((e for e in ENGINES.values() if is_loop_point_engine(e)), None)
    if eng is None:
        raise HTTPException(status_code=404, detail="loop-point engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        result = await eng.loop_point(
            raw, filename, min_loop_bars=min_loop_bars, num_candidates=num_candidates,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/midi/drum — step-sequencer spec → GM drum MIDI ──────────────────────


@app.post("/v1/midi/drum")
async def midi_drum(
    request: Request,
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
) -> Response:
    """Generate a MIDI drum pattern from a step-sequencer spec.
    Body: application/json or multipart with `spec` field.
    spec.pattern keys: kick, snare, hihat, hihat_open, ride, crash, clap, rim, cowbell..."""
    content_type = request.headers.get("content-type", "")
    if content_type.startswith("application/json"):
        try:
            spec = await request.json()
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid JSON body: {exc}") from exc
        output_path = request.query_params.get("output_path") or output_path
        output_url = request.query_params.get("output_url") or output_url
    else:
        form = await request.form()
        spec_raw = form.get("spec")
        if not spec_raw:
            raise HTTPException(
                status_code=400,
                detail="POST application/json or multipart with a `spec` field.",
            )
        try:
            spec = json.loads(str(spec_raw))
        except (ValueError, json.JSONDecodeError) as exc:
            raise HTTPException(status_code=400, detail=f"invalid `spec` JSON: {exc}") from exc
        output_path = str(form.get("output_path") or "") or output_path or None
        output_url = str(form.get("output_url") or "") or output_url or None

    eng = next((e for e in ENGINES.values() if is_drum_pattern_engine(e)), None)
    if eng is None:
        raise HTTPException(status_code=404, detail="drum-pattern engine not configured")

    try:
        midi_bytes = await eng.drum_pattern(spec)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await write_output(
        midi_bytes,
        media_type="audio/midi",
        filename="drum_pattern.mid",
        output_path=output_path,
        output_url=output_url,
        extra_json={"size": len(midi_bytes)},
    )


# ── /v1/audio/chords-to-midi — chord detection → MIDI chord progression ─────


@app.post("/v1/audio/chords-to-midi")
async def chords_to_midi(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    tempo_bpm: float | None = Form(default=None),
    velocity: int = Form(default=80),
    octave: int = Form(default=4),
) -> Response:
    """Detect chord progression in audio and export as a MIDI file.
    Each chord segment becomes a held chord (root + third + fifth) at the given octave.
    Requires chord-detect engine."""
    if velocity < 1 or velocity > 127:
        raise HTTPException(
            status_code=400,
            detail=f"velocity must be in [1, 127], got {velocity}",
        )
    if octave < 1 or octave > 7:
        raise HTTPException(
            status_code=400,
            detail=f"octave must be in [1, 7], got {octave}",
        )
    chord_eng = next((e for e in ENGINES.values() if is_chord_detect_engine(e)), None)
    if chord_eng is None:
        raise HTTPException(status_code=404, detail="chord-detect engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        chord_result = await chord_eng.detect_chords(raw, filename)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    chords = chord_result.get("chords", [])
    if not chords:
        raise HTTPException(status_code=400, detail="no chords detected in audio")

    bpm = float(tempo_bpm) if tempo_bpm is not None else 120.0
    if not (1.0 <= bpm <= 999.0):
        raise HTTPException(
            status_code=400,
            detail=f"tempo_bpm must be in [1, 999], got {bpm}",
        )

    try:
        midi_bytes = await asyncio.to_thread(
            chords_to_midi_bytes, chords,
            tempo_bpm=bpm, velocity=velocity, octave=octave,
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return await write_output(
        midi_bytes,
        media_type="audio/midi",
        filename="chords.mid",
        output_path=output_path,
        output_url=output_url,
        extra_json={
            "chord_count": len(chords),
            "key": chord_result.get("key", ""),
            "tempo_bpm": bpm,
            "size": len(midi_bytes),
        },
    )



# ── /v1/audio/deess — split-band de-esser ───────────────────────────────────


@app.post("/v1/audio/deess")
async def deess_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    threshold_db: float = Form(default=-20.0),
    frequency_hz: float = Form(default=6000.0),
    ratio: float = Form(default=4.0),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Split-band de-esser: compress sibilance above frequency_hz.
    threshold_db: level at which compression begins (dBFS, default -20).
    frequency_hz: highpass cutoff that isolates sibilance (default 6000 Hz).
    ratio: compression ratio (default 4.0)."""
    _validate_output_format(output_format)
    if not (1.0 <= ratio <= 50.0):
        raise HTTPException(
            status_code=400, detail=f"ratio must be in [1.0, 50.0], got {ratio}"
        )
    if not (1000.0 <= frequency_hz <= 16000.0):
        raise HTTPException(
            status_code=400,
            detail=f"frequency_hz must be in [1000, 16000], got {frequency_hz}",
        )
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    async def _produce() -> bytes:
        return await asyncio.to_thread(
            deess, raw, filename,
            threshold_db=threshold_db, frequency_hz=frequency_hz,
            ratio=ratio, output_format=output_format,
        )

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"deessed.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/deess",
        output_path=output_path,
        output_url=output_url,
        extra_json={"threshold_db": threshold_db, "frequency_hz": frequency_hz, "ratio": ratio},
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/audio/stereo-field — stereo field analysis ──────────────────────────


@app.post("/v1/audio/stereo-field")
async def stereo_field_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
) -> JSONResponse:
    """Analyse the stereo field: L/R correlation, width, balance, mono compatibility."""
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)
    try:
        result = await asyncio.to_thread(stereo_field, raw, filename)
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return JSONResponse(result)


# ── /v1/audio/thumbnail — extract most-interesting segment ──────────────────


@app.post("/v1/audio/thumbnail")
async def thumbnail_endpoint(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    file_url: str | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
    duration_sec: float = Form(default=30.0),
    output_format: str = Form(default="wav"),
    async_job: bool = Form(default=False),
    webhook_url: str | None = Form(default=None),
) -> Response:
    """Extract the most energetically interesting segment of duration_sec.
    Uses onset strength to locate the peak-activity region. Requires librosa-analyze."""
    _validate_output_format(output_format)
    if not (1.0 <= duration_sec <= 300.0):
        raise HTTPException(
            status_code=400,
            detail=f"duration_sec must be in [1, 300], got {duration_sec}",
        )
    eng = next((e for e in ENGINES.values() if is_thumbnail_engine(e)), None)
    if eng is None:
        raise HTTPException(status_code=404, detail="thumbnail engine not configured")
    raw, filename = await resolve_input(file=file, file_path=file_path, file_url=file_url)

    thumb_meta: dict[str, Any] = {}

    async def _produce() -> bytes:
        audio_bytes, meta = await eng.thumbnail(
            raw, filename, duration_sec=duration_sec, output_format=output_format,
        )
        thumb_meta.update(meta)
        return audio_bytes

    return await _run_with_optional_job(
        _produce,
        media_type=content_type_for(output_format),
        filename=f"thumbnail.{output_format}",
        job_ext=output_format,
        endpoint="/v1/audio/thumbnail",
        output_path=output_path,
        output_url=output_url,
        extra_json=thumb_meta,
        async_job=async_job,
        webhook_url=webhook_url,
    )


# ── /v1/midi/humanize — add timing jitter + velocity variation ───────────────


@app.post("/v1/midi/humanize")
async def midi_humanize(
    file: UploadFile | None = File(default=None),
    file_path: str | None = Form(default=None),
    timing_ms: float = Form(default=10.0),
    velocity_pct: float = Form(default=10.0),
    seed: int | None = Form(default=None),
    output_path: str | None = Form(default=None),
    output_url: str | None = Form(default=None),
) -> Response:
    """Add random timing jitter and velocity variation to MIDI notes.
    timing_ms: max ±timing offset per note in milliseconds (default 10).
    velocity_pct: max ±velocity change as % of 127 (default 10).
    seed: optional RNG seed for reproducibility."""
    if not (0.0 <= timing_ms <= 500.0):
        raise HTTPException(
            status_code=400, detail=f"timing_ms must be in [0, 500], got {timing_ms}"
        )
    if not (0.0 <= velocity_pct <= 50.0):
        raise HTTPException(
            status_code=400,
            detail=f"velocity_pct must be in [0, 50], got {velocity_pct}",
        )
    eng = next((e for e in ENGINES.values() if is_humanize_engine(e)), None)
    if eng is None:
        raise HTTPException(status_code=404, detail="humanize engine not configured")

    raw, _filename = await resolve_input(file=file, file_path=file_path, file_url=None)
    if not raw.startswith(b"MThd"):
        raise HTTPException(status_code=400, detail="input is not a MIDI file")

    try:
        result = await eng.humanize(
            raw, timing_ms=timing_ms, velocity_pct=velocity_pct, seed=seed
        )
    except AudioConversionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await write_output(
        result,
        media_type="audio/midi",
        filename="humanized.mid",
        output_path=output_path,
        output_url=output_url,
        extra_json={"timing_ms": timing_ms, "velocity_pct": velocity_pct},
    )


# ── /v1/batch — batch operations on staged files ────────────────────────────


@app.post("/v1/batch")
async def batch(request: Request) -> JSONResponse:
    """Execute a list of operations on staged files.
    Body is a JSON array of operation objects:
    [{"op": "convert", "file_path": "...", "output_path": "...", "output_format": "mp3"}, ...]
    Each op runs sequentially and returns its result or error.
    Supported ops: convert, normalize, trim, fade, reverse, speed, eq."""
    body = await request.body()
    try:
        ops = json.loads(body)
        if not isinstance(ops, list):
            raise ValueError("body must be a JSON array of operations")
    except (json.JSONDecodeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"invalid JSON: {exc}") from exc

    results = []
    for i, op_spec in enumerate(ops):
        if not isinstance(op_spec, dict):
            results.append({"index": i, "error": "operation must be an object"})
            continue
        op = op_spec.get("op", "")
        try:
            fp = op_spec.get("file_path") or None
            fu = op_spec.get("file_url") or None
            raw, fname = await resolve_input(file=None, file_path=fp, file_url=fu)
            out_path = op_spec.get("output_path") or None
            fmt = op_spec.get("output_format", "wav")
            _validate_output_format(fmt)

            if op == "convert":
                sr = op_spec.get("sample_rate")
                ch = op_spec.get("channels")
                b = await asyncio.to_thread(convert_audio, raw, fname, fmt, sr, ch)
            elif op == "normalize":
                target = float(op_spec.get("target_lufs", -14.0))
                loudness_eng = next((e for e in ENGINES.values() if is_loudness_engine(e)), None)
                if loudness_eng is None:
                    raise HTTPException(status_code=404, detail="loudness engine not configured")
                b, _ = await loudness_eng.normalize_lufs(raw, fname, target_lufs=target, output_format=fmt)
            elif op == "trim":
                ss = float(op_spec.get("start_sec", 0.0))
                es_raw = op_spec.get("end_sec")
                if es_raw is None:
                    raise ValueError("trim op requires 'end_sec'")
                es = float(es_raw)
                b = await asyncio.to_thread(trim_audio, raw, fname, ss, es, fmt)
            elif op == "fade":
                fi = float(op_spec.get("fade_in", 0.0))
                fo = float(op_spec.get("fade_out", 0.0))
                cv = op_spec.get("curve", "tri")
                b = await asyncio.to_thread(
                    fade_audio, raw, fname, fmt, fade_in=fi, fade_out=fo, curve=cv
                )
            elif op == "reverse":
                b = await asyncio.to_thread(reverse_audio, raw, fname, fmt)
            elif op == "speed":
                sp_raw = op_spec.get("speed")
                if sp_raw is None:
                    raise ValueError("speed op requires 'speed'")
                sp = float(sp_raw)
                b = await asyncio.to_thread(speed_audio, raw, fname, sp, fmt)
            elif op == "eq":
                bl = json.loads(op_spec.get("bands", "[]"))
                b = await asyncio.to_thread(eq_audio, raw, fname, fmt, bl)
            else:
                results.append({"index": i, "op": op, "error": f"unsupported op: {op!r}"})
                continue

            resp = await write_output(
                b, media_type=content_type_for(fmt),
                filename=f"batch_{i}.{fmt}",
                output_path=out_path, output_url=None,
            )
            if isinstance(resp, JSONResponse):
                resp_data = json.loads(resp.body)
            else:
                resp_data = {"size": len(resp.body)}
            results.append({"index": i, "op": op, "status": "ok", **resp_data})
        except HTTPException as exc:
            results.append({"index": i, "op": op, "error": exc.detail})
        except AudioConversionError as exc:
            results.append({"index": i, "op": op, "error": str(exc)})
        except Exception as exc:
            results.append({"index": i, "op": op, "error": f"unexpected error: {exc}"})

    return JSONResponse({"results": results})


# ── GET /v1/jobs — list all jobs ─────────────────────────────────────────────


@app.get("/v1/jobs")
async def jobs_list(status: str | None = None) -> JSONResponse:
    """List all async jobs, optionally filtered by status.
    status: pending, running, completed, failed, cancelled."""
    jobs = await JOB_QUEUE.list_jobs(status=status)
    return JSONResponse({"jobs": jobs})


# ── GET /v1/jobs/{job_id} — poll job status ───────────────────────────────────


@app.get("/v1/jobs/{job_id}")
async def jobs_get(job_id: str) -> JSONResponse:
    """Get status and result of an async job by ID."""
    job = await JOB_QUEUE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")
    return JSONResponse(job.to_dict())


# ── DELETE /v1/jobs/{job_id} — cancel or delete a job ────────────────────────


@app.delete("/v1/jobs/{job_id}")
async def jobs_delete(job_id: str) -> JSONResponse:
    """Cancel a running job or remove a completed/failed job from the queue."""
    job = await JOB_QUEUE.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"job {job_id!r} not found")
    cancelled = await JOB_QUEUE.cancel(job_id)
    if cancelled:
        return JSONResponse({"job_id": job_id, "cancelled": True})
    # Already terminal — remove it
    job_dict = job.to_dict()
    job_dict["deleted"] = True
    # Force removal by marking it completed_at far in the past so cleanup catches it
    job.completed_at = 0.0
    await JOB_QUEUE.cleanup(0)
    return JSONResponse({"job_id": job_id, "deleted": True})


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

MCP_SERVER = build_mcp_server(engines=ENGINES, registry=REGISTRY, presets=PRESETS)
app.mount("/v1/mcp", MCP_SERVER.streamable_http_app())
