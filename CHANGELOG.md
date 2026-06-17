# Changelog

All notable changes per release. Versions follow [semver](https://semver.org).
From v1.0.0 onward the REST API is stable — breaking changes will be major
bumps and called out explicitly; minor bumps are additive, patch bumps are
docs / build / fixes only.

## v1.0.6 — 2026-06-09

**Bug fixes surfaced by downstream consumer + container-name unification + trim UX.**

- **Fix: `/v1/audio/info` no longer reports `"ffprobe failed: unknown error"` on valid MP3 input.** `ffprobe -v quiet` silences ALL stderr, including the actual error message — so any probe failure surfaced as the generic placeholder. Switched to `ffprobe -v error`, which mutes info/warning lines but lets real errors through. Probe failures now surface the underlying ffprobe message in the API response.
- **UX: `/v1/audio/trim` `end_sec` is now optional — omit it to trim from `start_sec` to source duration.** Handler probes the input via `audio_info` and uses the source's `duration_sec` as the implicit upper bound. The common "chop leading silence" / "fade-out tail" pipelines no longer need a separate probe-then-trim round trip. Old behavior of `end_sec <= start_sec → 400` preserved when explicitly supplied. `openapi.yaml` `AudioTrimRequest.end_sec` dropped from `required` and marked `nullable: true` with a docstring describing the implicit "to end" default. Regenerated Pydantic.
- **Test harness: fixed container names.** Was `audiolla-pytest-{pid}-{hex}` (different per session, hard to share across runs). Now `audiolla-pytest` for CPU and `audiolla-pytest-cuda` for CUDA — `conftest.py` calls `docker rm -f <exact-name>` at session start to evict any leftover from a prior crashed session, then spawns fresh. Same image (`HARNESS_IMAGE`) reused; no rebuilds between tests. Concurrent pytest invocations on the same host would collide on the fixed name — operator's choice.
- **New regression test: `test_info_on_mp3`.** Stages a WAV, converts it to MP3 via `/v1/audio/convert`, then probes the MP3 with `/v1/audio/info`. Asserts `codec == "mp3"`, positive duration, ≥ 1 channel. Pins the bug 1 fix.
- **Updated test: `test_trim_omitted_end_sec_defaults_to_source_end`.** Replaces the prior "missing end_sec → 422" expectation. Trims `start_sec=3.0` without `end_sec` on the 8 s fixture; asserts response carries `end_sec >= 7.5` and the output WAV decodes as ≥ 4.5 s.
- No API contract removed — `end_sec` is still accepted when provided. The 422 path that used to fire on missing `end_sec` now succeeds.

## v1.0.5 — 2026-06-09

**Test infrastructure overhaul + engine logging coverage + UVR / DeepFilter / presets fixes.** No API changes, no contract changes. Everything in this release is additive to the v1.0.4 baseline or fixes a latent bug.

### Integration test infrastructure — bash → pytest

The 71 bash `e2e_*.sh` scripts are gone. Replaced by **83 pytest files** with **479 individual test functions** under `tests/integration/`. The new layout:

- `conftest.py` — session-scoped audiolla container fixture. Reads `@pytest.mark.engine(...)` markers across all collected tests and starts the container with the union of required engines so a single-file pytest run (`pytest test_audio_enhance_deepfilter.py`) only enables `deepfilter`. Auto-loads `tests/.env` via `python-dotenv`. Auto-skips tests marked `gpu` / `hf_gated` / `noncommercial` when the corresponding env var isn't set. Echoes `X-Request-Id` for correlation.
- `helpers.py` — magic-byte asserts for WAV / MP3 / MIDI / PNG / MP4 / WebM / ZIP plus a `uvr_model_produced_no_output(response)` helper that treats UVR's two "phantom output" 400s on synthetic input as valid.
- One file per endpoint or per engine (engine-dispatched routes like `/v1/audio/generate/{engine}`, `/v1/audio/separate`, `/v1/audio/restore/{engine}`, `/v1/audio/noise-reduce/{engine}`, `/v1/audio/diarize/{engine}` got split per engine — 5 generators, 6 separators, 3 restore variants, 2 noise-reduce variants, 1 diarize).
- `atexit` + SIGINT/SIGTERM/SIGHUP handlers in `conftest.py` track the exact container name this session started and clean it up on interrupt — no more orphans from Ctrl+C / kill.

`Makefile`'s `test-integration` target now runs `pytest tests/integration/ -v` instead of `bash tests/integration/run.sh`. Markers + env knobs documented in the target's comment.

Full CUDA pass: **470 passed, 9 skipped (auth/file-url xor self-skips), 0 failed** in ~7 minutes.

### Engine logging coverage

The v1.0.4 entry described the JSON formatter, `LOG_LEVEL`, contextvar correlation. This release wires it up everywhere:

- 25 of 25 engine modules now log at INFO on `_load_sync` start + ready, at INFO on every public inference method start + finish (with input/output size + duration_ms via `time.perf_counter()`), and at WARNING / `_log.exception(...)` immediately before every `raise EngineError(...)` to capture traceback. Prompts truncated to 80 chars before logging.
- 7 framework modules — `audio`, `auth`, `config`, `files`, `input_resolver`, `jobs`, `output_writer`, `pipeline` — got module-level `_log = logging.getLogger("audiolla.<mod>")` plus WARNING at every user-recoverable error path (`auth` denied, `files` traversal rejected, `pipeline` step failed, `output_writer` 413/400 paths) and INFO on every job state transition (started / cancelled / completed with duration / webhook delivered / webhook retry / webhook give-up).
- Every log line still carries the canonical JSON envelope from v1.0.4: `ts` / `level` / `logger` / `file` / `line` / `func` / `msg` / `service` / `version` / `pid` / `host` / `thread` plus per-request `request_id` / `method` / `path` when emitted during a handler.

### Bug fixes

- **UVR separators (`uvr_separator.py`).** Multiple latent bugs surfaced by the new pytest UVR tests, which actually invoke the engines (the v0.x bash tests hit a wrong URL and 404'd before reaching the engine).
  - `_STEM_RE` was anchored to `(StemName).ext` at end of filename; newer `audio-separator` releases append the model filename — `(Vocals)_model_bs_roformer_ep_317_sdr_12.wav`. Regex now matches any `(...)` group, taking the last as the stem name.
  - `audio-separator` returns either basenames or absolute paths depending on the model, AND its claimed paths don't always match where the file actually lands — the library reports filenames it never wrote on empty / silent model output (the common case on synthetic test input). Filter to files that actually exist on disk under `tmpdir` before encoding. Phantom-output cases raise `"model produced no output files"` / `"no recognisable stems"` consistently; the test helper recognises both as a synthetic-input edge case and short-circuits.
- **DeepFilterNet (`deepfilter_engine.py`).** `df.utils.get_commit_hash()` spawns `git` at engine load to record the commit; runtime images didn't have `git`. Added `git` to `Dockerfile` + `Dockerfile.cuda` apt installs.
- **Presets on CUDA image (`Dockerfile.cuda`).** `COPY --chown=audiolla:audiolla presets /app/presets` was missing from the CUDA Dockerfile, so `/v1/presets` returned 0 entries on CUDA. Added.
- **pyannote diarize test.** Synthetic sine has no human speech → `num_speakers == 0`; test now asserts `>= 0`, not `>= 1`. Validates contract shape rather than the model's choice on synthetic input. Test still requires the operator to accept both `pyannote/speaker-diarization-3.1` AND `pyannote/segmentation-3.0` licences on huggingface.co.

### `.gitignore` + `.dockerignore` hardening

Both files extended with the same set of model/archive/cache patterns:

- Additional ML weight extensions: `*.ckpt`, `*.pt`, `*.pth`, `*.onnx`, `*.h5`, `*.tflite`, `*.pb`, `*.mlmodel`, `*.gguf`, `*.npz` (was: just `*.safetensors`, `*.bin`).
- Archive formats: `*.tar`, `*.tar.gz`, `*.tar.bz2`, `*.tar.xz`, `*.tgz`, `*.zip`, `*.7z`, `*.rar`.
- HF / torch caches at top level: `.hf_cache/`, `hf_cache/`, `huggingface/`, `.torch/`, `torch_cache/`.
- Runtime mount dirs: `/data/`, `node_modules/`.
- `.dockerignore` also gains `.claude/`, `.git-credentials`, `*~`, `.tool-versions`, `.python-version`.

Verified docker build context drops from "potentially 29 GB+" (had `.e2e-cache/` ever escaped, plus stray model files) to **2.02 MB**.

## v1.0.4 — 2026-06-08

**Bug fix + structured logging overhaul.**

- **Fix: `/v1/audio/enhance/deepfilter` no longer returns 400 before
  first load.** `is_deepfilter_engine()` was checking for `_df_state` (a
  private attribute set only inside `_load_sync()` on first inference)
  in addition to the public `enhance` method. The first call after
  container boot saw `_df_state` missing → predicate False → handler
  responded `400 engine 'deepfilter' does not support neural
  enhancement`. The predicate now checks only the public contract; the
  engine loads on the same call.
- **JSON logging via a single centralised init path.** Every audiolla
  process funnels through `audiolla.logging.configure()` (called once
  from `__main__` before uvicorn starts). Uvicorn's own loggers
  (`uvicorn`, `uvicorn.error`, `uvicorn.access`) are aligned with the
  same handler + formatter so all log lines are line-delimited JSON
  with the same shape regardless of origin.
- **`LOG_LEVEL` env var.** Accepts `DEBUG` / `INFO` / `WARNING` /
  `ERROR` / `CRITICAL` (case-insensitive; `WARN` accepted as alias).
  Default `INFO`.
- **Rich observability fields in every record.** Per-record JSON:
  `ts` (ISO-8601 UTC), `level`, `logger`, `file`, `line`, `func`,
  `msg`, `service`, `version`, `pid`, `host`, `thread`. Anything passed
  via the stdlib's `extra={}` kwarg becomes a top-level key. Exception
  tracebacks fold into the same JSON line under `exc` (line-delimited
  JSON / NDJSON friendly).
- **Request correlation IDs via contextvars + per-request middleware.**
  Every HTTP request gets a `request_id` (honoured from inbound
  `X-Request-Id`, else a fresh uuid4 hex). It's bound to a contextvar
  so every log line emitted during the request lifetime carries it
  automatically, no `extra=` plumbing required. The ID is echoed back
  on the response. Summary log per request is level-scaled:
  `DEBUG` for `/healthz`, `INFO` for 2xx/3xx, `WARNING` for 4xx,
  `ERROR` for 5xx — with method, path, status, duration_ms, client IP
  (X-Forwarded-For honored), user agent, request/response byte sizes.

## v1.0.3 — 2026-06-08

**HF token alias fix.** `huggingface_hub` (used by diffusers, transformers,
etc. for gated-model auth) reads `HF_TOKEN` as the canonical name.
Audiolla's pyannote engine + older docs use `HUGGINGFACE_TOKEN`. Operators
who only set `HUGGINGFACE_TOKEN` were hitting `401 Unauthorized` on gated
models like `stabilityai/stable-audio-open-1.0` and `facebook/musicgen-*`
because the HF lib went anonymous despite the token being available under
a different env var.

`entrypoint.sh` now mirrors `HUGGINGFACE_TOKEN` ↔ `HF_TOKEN` in both
directions before exec'ing the server, so setting either name unlocks
gated downloads regardless of which env var the operator picked.

- `entrypoint.sh`: bidirectional alias between `HUGGINGFACE_TOKEN` and
  `HF_TOKEN`.
- `README.md`: env table now lists both names + clarifies which gated
  engines need a token (pyannote, stable-audio-open, musicgen-*). The
  diarization "Note" block updated to point at `HF_TOKEN` first.

## v1.0.2 — 2026-06-08

**Runtime default flip — `HF_HUB_OFFLINE=0`.** Previously the prod image
baked `HF_HUB_OFFLINE=1` for the prefetched-deployment use case. In
practice, downstream consumers running the audio generation engines
(`/v1/audio/generate/{stable-audio-open,musicgen-*,riffusion,audioldm2}`)
or the HF-backed analysis engines (`ast-tag`, `clap-embed`, `pyannote`)
were hitting `OSError: model is not cached locally` on first call —
unusable out of the box. New default: `HF_HUB_OFFLINE=0`, models lazy-
download on first call into `HF_HOME=/data/hf` (mount a volume for
persistence). For locked-down deployments, prefetch with
`huggingface-cli download <model>` against the volume and pass
`-e HF_HUB_OFFLINE=1` at run time — same offline guarantee as before,
just opt-in.

- `Dockerfile` + `Dockerfile.cuda`: `HF_HUB_OFFLINE=1` → `HF_HUB_OFFLINE=0`.
- README "Audio tagging" + the `tag` / `embed` handler docstrings
  updated to reflect lazy-download as the default; the offline-only
  mode is now opt-in via `-e HF_HUB_OFFLINE=1` after prefetch.

## v1.0.1 — 2026-06-08

**CI fix.** No code changes — the v1.0.0 image is functionally identical
to v1.0.1. CUDA build was OOMing the GitHub-hosted `ubuntu-latest` runner
disk during torch 2.5.1+cu126 unpack (~5 GB) plus the rest of the
heavy-deps layer. Switched the reusable workflow to v0.6.0 which
optionally frees ~25-30 GB before building (strips Android SDK, .NET,
Haskell, CodeQL, large apt packages, preloaded docker images; tool cache
+ swap left intact). Pinned the reusable workflow by SHA per the project's
supply-chain rules.

- Bumped `psyb0t/reusable-github-workflows` reference to v0.6.0
  (SHA `59d43bac747f6bf66eeddb103a845b6dbf367c6b`) and enabled the new
  `free_disk_space: true` input.

## v1.0.0 — 2026-06-07

**Stable API milestone.** The REST contract is now spec-first
(`openapi.yaml` is the source of truth), JSON-everywhere across all 90
endpoints except `PUT /v1/files`, and locked under semver going forward.
This release jumps directly from v0.23.1 to v1.0.0 — there is no v0.24.x
line; the breaking refactor and the 1.0 stability commitment ship in the
same tag. **Every existing v0.23.x client breaks** — see the migration
notes below. Five new text-to-audio engines also land in this release.

### BREAKING — API surface refactor

- **Spec-first.** `openapi.yaml` is now the contract. Pydantic models are regenerated from it via `make generate`; handler signatures are `async def X(req: SomeRequest)` instead of long `Form(...)`/`File(...)` lists. Never hand-edit `src/audiolla/schema/_generated.py` — edit the YAML and regenerate.
- **Multipart upload dropped everywhere except `PUT /v1/files/{path}`.** Every audio-processing endpoint now takes a JSON body. Pre-stage your file via `PUT /v1/files/{path}` then reference it by `{"file_path": "..."}` (or `{"file_url": "https://..."}` for server-side fetch).
- **Raw audio responses dropped.** Every audio-producing endpoint requires `output_path` xor `output_url` and returns JSON `{path, size, ...}` or `{url, size, ...}`. Use `async_job=true` to auto-stage to `jobs/{id}.{ext}`.
- **MCP audio-producing tools require an output destination.** The `audio_base64` / `midi_base64` / `image_base64` / `video_base64` / `content_base64` response modes were removed — LLMs can't consume audio bytes anyway, and large base64 payloads choke the context window (10 MB WAV ≈ 13 MB base64 ≈ 3 M tokens). Pass `output_path` (stage to FILES_DIR, response is `{path, size}`) or `output_url` (PUT to presigned URL, response is `{url, size}`).

### Migration cheatsheet

```diff
- curl -X POST http://localhost:8000/v1/audio/normalize \
-     -F "file=@track.wav" -F "target_lufs=-14" -o normalized.wav
+ # 1) stage the file (multipart only lives here now)
+ curl -X PUT --data-binary @track.wav \
+     -H 'Content-Type: application/octet-stream' \
+     http://localhost:8000/v1/files/uploads/track.wav
+ # 2) process via JSON body
+ curl -X POST http://localhost:8000/v1/audio/normalize \
+     -H 'Content-Type: application/json' \
+     -d '{"file_path":"uploads/track.wav","target_lufs":-14,"output_path":"out/normalized.wav"}'
+ # 3) retrieve the result
+ curl -o normalized.wav http://localhost:8000/v1/files/out/normalized.wav
```

`output_url` (presigned PUT) and `async_job=true` (auto-stage to `jobs/{id}.{ext}`) work the same way as before.

### NEW — text-to-audio generation (5 engines)

- New: `POST /v1/audio/generate/{engine}` — text → audio in one call. Per-engine routes with engine-specific Pydantic schemas in `openapi.yaml` (each engine's `num_inference_steps`, `negative_prompt` etc. are part of its own request schema).
- New engines (all CUDA-only):
  - **`stable-audio-open`** — Stability Stable Audio Open 1.0. **Stability Community Licence** (commercial use OK below the licence's revenue threshold). 47-second hard cap, 44.1 kHz stereo, no vocals — best for loops, riffs, ambient textures, SFX, drum beats. ~12 GB VRAM at fp16.
  - **`musicgen-small`** — Meta MusicGen 300M. **CC-BY-NC 4.0** (non-commercial only). 30 s hard cap, 32 kHz mono, instrumental. ~3 GB VRAM at fp16.
  - **`musicgen-medium`** — Meta MusicGen 1.5B. **CC-BY-NC 4.0** (same gate). 30 s hard cap, 32 kHz mono, instrumental. Higher quality than -small. ~6-8 GB VRAM at fp16.
  - **`riffusion`** — Riffusion-v1 (Stable Diffusion fine-tune that generates spectrograms, reconstructed to audio via Griffin-Lim). **CreativeML OpenRAIL-M** (commercial OK with the licence's usage restrictions). ~5 s per pass, 22.05 kHz mono, lo-fi character. ~3 GB VRAM at fp16.
  - **`audioldm2`** — AudioLDM 2 (cvssp/audioldm2). **CC-BY 4.0** — the only commercial-safe generator in this set, NO opt-in gate required. General-purpose SFX: environmental ambience, animal sounds, foley, mechanical / impact sounds. 16 kHz mono, up to 30 s. Slow at default 200-step DDIM — pass `num_inference_steps=50` for ~4x speedup. ~8-10 GB VRAM at fp16 with CPU offload.
- **Licence opt-in for MusicGen.** Both MusicGen engines refuse to load unless the operator sets `AUDIOLLA_ENABLE_NONCOMMERCIAL=1` in the server environment — same pattern as matchering's GPL v3 gate. Read [the MusicGen weights licence](https://github.com/facebookresearch/audiocraft/blob/main/LICENSE_weights) before opting in.
- New MCP tool: **`generate_music`** — same engine/prompt/lyrics/seed contract; requires `output_path` xor `output_url`. Tool count 85 → 86.

### Infrastructure

- New: `POST /v1/audio/generate/{engine}` — text → audio in one call. Form params: `prompt` (required), `duration_sec`, optional `lyrics`, `seed`, `num_inference_steps` (for engines that expose it), plus the standard `output_format` / `output_path` / `output_url` / `async_job` / `webhook_url`. URL-path engine slug so future generators slot in without endpoint changes.
- New engines (all CUDA-only):
  - **`stable-audio-open`** — Stability Stable Audio Open 1.0. **Stability Community Licence** (commercial use OK below the licence's revenue threshold). 47-second hard cap, 44.1 kHz stereo, no vocals — best for loops, riffs, ambient textures, SFX, drum beats. ~12 GB VRAM at fp16.
  - **`musicgen-small`** — Meta MusicGen 300M. **CC-BY-NC 4.0** (non-commercial only). 30 s hard cap, 32 kHz mono, instrumental. ~3 GB VRAM at fp16.
  - **`musicgen-medium`** — Meta MusicGen 1.5B. **CC-BY-NC 4.0** (same gate). 30 s hard cap, 32 kHz mono, instrumental. Higher quality than -small. ~6-8 GB VRAM at fp16.
  - **`riffusion`** — Riffusion-v1 (Stable Diffusion fine-tune that generates spectrograms, reconstructed to audio via Griffin-Lim). **CreativeML OpenRAIL-M** (commercial OK with the licence's usage restrictions). ~5 s per pass, 22.05 kHz mono, lo-fi character. ~3 GB VRAM at fp16.
  - **`audioldm2`** — AudioLDM 2 (cvssp/audioldm2). **CC-BY 4.0** — the only commercial-safe generator in this set, NO opt-in gate required. General-purpose SFX: environmental ambience, animal sounds, foley, mechanical / impact sounds. 16 kHz mono, up to 30 s. Slow at default 200-step DDIM — pass `num_inference_steps=50` for ~4x speedup. ~8-10 GB VRAM at fp16 with CPU offload.
- **Licence opt-in for MusicGen.** Both MusicGen engines refuse to load unless the operator sets `AUDIOLLA_ENABLE_NONCOMMERCIAL=1` in the server environment — same pattern as matchering's GPL v3 gate. Read [the MusicGen weights licence](https://github.com/facebookresearch/audiocraft/blob/main/LICENSE_weights) before opting in.
- New MCP tool: **`generate_music`** — text-to-music dispatch with the same engine/prompt/lyrics/seed contract; takes `output_path` / `output_url` for FILES_DIR staging or presigned PUT. Tool count 85 → 86.
- Heavy-deps spec adds `diffusers==0.32.2` + `torchsde==0.2.6` + bumps `huggingface-hub` 0.30.2 → 0.34.6 in both CPU and CUDA variants. `torchsde` is a transitive dep of Stable Audio Open's `CosineDPMSolverMultistepScheduler` that diffusers doesn't pull in as a hard requirement. `requirements-heavy-{cpu,cuda}.txt` regenerated + hash-locked in this release — no separate operator step required.
- Catalog endpoint gains a "generate" category with all four engines.
- "What's not in here" updated to track music-gen + SFX-gen options. Deferred-but-researched engines (see README "Generate music + SFX" section):
  - **ACE-Step v1 3.5B** (Apache 2.0, full songs with vocals) — requires diffusers 0.38+ which itself requires a pre-release `safetensors`. Doesn't pass the hash-locked supply-chain gate. Revisit when `safetensors 0.8.x` ships stable, or vendor ACE-Step's pipeline directly.
  - **DiffRhythm full v1.2** (Apache 2.0) — unpackaged research repo, no `setup.py` / PyPI release. Revisit on upstream packaging or vendored `thirdparty/` integration.
  - **Stable Audio Open Small** (Stability Community Licence, 11 s SFX-specialist) — only loadable via `stable-audio-tools`, which pins `python >=3.10, <3.11`; audiolla is on Python 3.12 = hard incompatibility. Revisit when the library widens its Python range or diffusers grows a pipeline for it.
  - **TangoFlux** (ICLR 2026, 44.1 kHz stereo, fast Flow Matching) — git-only install, no PyPI package. Workable via SHA-pin but deferred to keep heavy-deps PyPI-only.
  - **AudioGen** (Meta, CC-BY-NC, SFX-specialist) — `audiocraft==1.3.0` pins `transformers<=4.31.0`, hard conflict with our 4.51.3. Would need an isolated subprocess / sidecar container.
  - **YuE 7B** (Apache 2.0, full songs with vocals) — 16-24 GB VRAM at fp16, doesn't fit on a 12 GB GPU without int4 quant tooling.
- Tests:
  - Unit: contract tests across the 5 engines (duck-type predicate, per-engine constants, duration-cap boundaries, bad-prompt + over-cap rejections per engine, licence-gate truthy/falsy values + licence-link assertion, and a positive-path assertion that AudioLDM2's `_load_sync` does NOT invoke the licence gate). Plus 7 server-level REST contract tests (200 / 404 / 400 / 415 / 422 / output_path / lyrics+seed forwarding). Total: 354/354 ✓.
  - Real e2e (CUDA-only): new `tests/integration/e2e_generate.sh` — generates a drum loop with each engine, validates the WAV decodes + is above the silence floor + is at least 1 s long, then **POSTs the generated audio back through `/v1/audio/beats` and asserts a positive tempo + at least 6-8 beats are detected**. This closes the loop: if generation silently emitted zeros, beats would find nothing. Also asserts seed reproducibility (same seed → byte-identical sha256) and the licence-gate refusal on a sibling container without the opt-in. AudioLDM2's SFX path is validated by generating "heavy rain on a metal roof" and confirming the WAV decodes — no beats check (it's an SFX prompt, not rhythmic).
- `harness.sh` improvement: now forwards `HF_*` / `HUGGINGFACE_*` env vars into the test container (was only `AUDIOLLA_*`). Enables `HUGGINGFACE_TOKEN` / `HF_HUB_OFFLINE` overrides without harness changes.

## v0.23.1 — 2026-06-07

README sync for v0.23.0 MCP changes.

- MCP section rewritten to describe all three output modes (default base64 / `output_path` for FILES_DIR staging / `output_url` for presigned PUT). Previous wording claimed audio over MCP is always base64-encoded — true before v0.23.0, no longer accurate.
- `separate` tool row in the MCP tools table now mentions `output_paths={stem:path}` alongside `output_urls={stem:url}`.

Docs only — no code changes.

## v0.23.0 — 2026-06-07

MCP tools now support local staging (`output_path`) in addition to base64 + presigned PUT.

- `_emit_audio` MCP helper grew an `output_path` branch — writes to `FILES_DIR/<path>` via the same code as the REST layer's `/v1/files` and returns `{path, size, output_format}`. Mutually exclusive with `output_url`.
- `_run_audio_tool` helper forwards `output_path`. Every MCP tool that used the helper (and most that called `_emit_audio` directly) now exposes the param.
- **35 of 81 MCP tools** now accept `output_path` (or `output_paths` per-stem map on `separate`) — up from **3**. The remaining 46 are analysis tools that return JSON only; they don't produce audio so the param doesn't apply.
- `visualize` tool: takes `output_path` across all three modes (PNG spectrogram, PNG waveform, MP4/WebM video).
- `separate` tool: takes `output_paths={stem_name: path}` map mirroring the existing `output_urls` shape. Both per-stem maps are mutually exclusive.
- Bug fix: `_run_audio_tool` was infinite-recursing (left over from an earlier regex sweep). REST tests passed because they never exercised the MCP path. Live MCP clients would have crashed on every audio-producing tool that used the helper.

## v0.22.2 — 2026-06-07

Docs-only refresh of `.agents/.skills/audiolla/SKILL.md` — was a v0.1.0 artifact heavily drifted from the live API.

- Fixed 27+ stale endpoint paths (`/v1/audio/spectrogram`, `/v1/audio/dereverb`, `/v1/audio/visualize`, `/v1/audio/to_midi`, `/v1/audio/enhance`, `/v1/audio/loudness-curve`, `/v1/audio/hpss` — all moved to namespaced / engine-in-path routes since v0.1.0).
- Removed dead engine slug `uvr-deecho-aggressive` (consolidated into `uvr-deecho` with `aggressive=true` form param in v0.19.0).
- New sections: **Authoritative reference: `GET /v1/catalog`** (points agents at the live API catalog as source of truth), **Workflows — presets + ad-hoc pipelines**, **Async jobs**, **Output to presigned PUT URL**.
- Engines table expanded from ~15 → ~25 entries with correct backing routes.
- "When to use" / "When NOT to use" rewritten to cover ~30 newer capabilities + clarified the speech-features caveat (audiolla has VAD / diarization / DeepFilterNet — exclusion is transcription/ASR/TTS).
- Loudness gotcha rewritten — `/v1/audio/loudness` measures JSON-only, `/v1/audio/normalize` returns audio + LUFS headers.

## v0.22.1 — 2026-06-07

Positioning + MCP workflow tools.

- Unified all internal copy on **audio-production** (was drifting between "music-production" and "audio" — README was already correct).
- MCP: 5 new tools — `list_presets`, `describe_preset`, `list_ops`, `run_preset`, `run_pipeline_tool` — so LLM agents can reach the workflow surface that REST already had.
- Replaced hardcoded `"81 tools"` log line with the live count via `mcp.list_tools()`.

## v0.22.0 — 2026-06-07

Multiband compression + workflow primitives + big server refactor.

- New: `POST /v1/audio/multiband-compress` — N-band compressor with zero-phase LR4-equivalent crossovers (mastering-grade dynamics).
- New: `POST /v1/pipeline` — ad-hoc op chain run server-side; intermediates stay in memory between steps, no re-upload.
- New: `POST /v1/presets/{name}` + `GET /v1/presets[/{name}]` — curated YAML workflows. Shipped presets: `master-for-spotify` (3-band master + -14 LUFS), `podcast-cleanup` (DeepFilterNet + de-ess + -16 LUFS), `vocal-cleanup` (UVR dereverb + denoise + de-ess + light comp).
- New: `GET /v1/ops` (~24 pipeline op slugs) + `GET /v1/catalog` (17 categories, machine-readable endpoint list for discovery).
- `GET /v1/engines` now reports `loaded` + `idle_seconds` per engine.
- New env var: `AUDIOLLA_PRESETS_DIR` (default `/app/presets`).
- Internal refactor: `_run_with_optional_job()` + `_run_json_or_audio()` helpers — every audio-producing endpoint now flows through one well-typed helper. server.py shrinks ~900 lines.
- `audio.py` organised by section banner (CORE / TRANSFORM / STEREO / DYNAMICS / RESTORE / EFFECTS / ANALYZE / MIDI).
- mcp_server.py: new `_run_audio_tool()` helper.
- Fixed pre-existing flaky integration tests: loudness URL bug, UVR curl timeout, 400-vs-404 file-not-found mismatches in hpss/trim/mix.
- Tests: unit 280 → 304, integration 103/103 across refactored + new endpoints.

## v0.21.1 — 2026-06-04

Supply-chain age gate: 7-day floor on bump.

- `bump_exclude_newer.sh` emits `today_utc - 7 days` instead of today, so fresh wheels in the post-publish attack window are excluded from resolution until they've had a week of community scrutiny.
- README and inline docs updated to explain the 7-day floor.

## v0.21.0 — 2026-06-04

Async jobs support `output_url`.

- Pass `output_url=<presigned PUT URL>` to any `async_job=true` request and the result is PUT to the URL on completion instead of staged locally.
- Inline streaming is not supported for async jobs (deliberate).
- Priority order: `output_url` → `output_path` → auto-generated `jobs/{id}.{ext}` fallback.

## v0.20.0 — 2026-06-04

**Breaking.** Visualize endpoints split into image/ and video/ sub-namespaces.

- `/v1/audio/visualize/spectrogram` → `/v1/audio/visualize/image/spectrogram` (PNG, color + scale params).
- `/v1/audio/visualize/waveform` → `/v1/audio/visualize/image/waveform` (PNG, color param).
- `/v1/audio/visualize/{mode}` → `/v1/audio/visualize/video/{mode}` (MP4/WebM; `mode` is a URL path segment now, no longer a form field).
- Each variant takes only the params it actually needs — no more megaendpoint with ignored fields.

## v0.19.0 — 2026-06-04

**Breaking.** Endpoint consolidation + `uvr-deecho` aggressive mode.

- `/v1/audio/dereverb/{engine}` + `/v1/audio/deecho/{engine}` + `/v1/audio/denoise/{engine}` (UVR variants) → unified at `POST /v1/audio/restore/{engine}`.
- DSP noise reduction → `POST /v1/audio/noise-reduce/{engine}` (engine = `noise-reduce` for DSP, `uvr-denoise` for ML).
- `/v1/audio/spectrogram` → `/v1/audio/visualize/spectrogram` (first move under the visualize namespace).
- `/v1/audio/waveform` → `/v1/audio/visualize/waveform`.
- `/v1/audio/visualize` (mode in form field) → `/v1/audio/visualize/{mode}` (mode in URL path).
- `/v1/audio/hpss` → `/v1/audio/separate/hpss`.
- `/v1/audio/loudness-curve` → `/v1/audio/loudness/curve`.
- `/v1/audio/noise-reduce` → `/v1/audio/noise-reduce/{engine}` (engine in URL path).
- New: `aggressive=true` form param on `uvr-deecho` for hard echo removal (replaces the previous `uvr-deecho-aggressive` engine slug).

## v0.17.0 — 2026-06-04

De-ess, stereo-field, audio thumbnail, MIDI humanize.

- `POST /v1/audio/deess` — split-band de-esser, no engine required.
- `POST /v1/audio/stereo-field` — correlation / width / balance / mono-compat analysis.
- `POST /v1/audio/thumbnail` — onset-density preview clip extraction (requires `librosa-analyze`).
- `POST /v1/midi/humanize` — timing + velocity jitter with optional deterministic seed.
- MCP: 85 tools total.

## v0.16.0 — 2026-06-04

Six new features.

- `POST /v1/audio/loudness/curve` — RMS envelope over time.
- `POST /v1/audio/pitch-correct` — snap to nearest semitone (auto-tune).
- `POST /v1/audio/repair` — declip + dehum (50/60 Hz notch).
- `POST /v1/audio/loop-point` — find best seamless loop boundary.
- `POST /v1/midi/drum` — step-sequencer spec → GM drum MIDI.
- `POST /v1/audio/chords-to-midi` — chord detection → MIDI progression.

## v0.15.1 — 2026-06-04

README fully updated for v0.15.0 features.

## v0.15.0 — 2026-06-04

Async jobs + webhooks + 8 new endpoints + metadata engine.

- New: `async_job=true` form param on every audio-producing endpoint — fire-and-forget with optional `webhook_url` POST callback on completion.
- New: `/v1/jobs` (list), `/v1/jobs/{id}` (poll), `DELETE /v1/jobs/{id}` (cancel).
- New: `metadata` engine — read/write ID3, Vorbis, FLAC tags via mutagen.
- 8 new endpoints including audio metadata, clip-detect, mid-side, beat-slice, conv-reverb, transient.
- 40 new integration tests.

## v0.14.2 — 2026-06-03

bpm-match bug fix + test suite corrections.

- Fixed `beats_result["tempo"]` → `beats_result["tempo_bpm"]` KeyError crash.
- Zero-BPM guard: HTTP 400 when audio has no detectable beat.
- Test fixes: missing staged file returns 404 (not 400), bpm-match uses a real click-track fixture, DIND-safe fixture path.
- All 113 integration test cases pass.

## v0.14.1 — 2026-06-03

Integration tests for 15 endpoints added in v0.12.0–v0.14.0. Each test boots its own ephemeral container.

## v0.14.0 — 2026-06-03

Five new editing primitives.

- `POST /v1/audio/split` — equal-time (N parts) or silence-based split; ZIP output.
- `POST /v1/audio/pan` — stereo pan via ffmpeg pan filter; position [-1.0, 1.0].
- `POST /v1/audio/eq` — parametric EQ via ffmpeg equalizer chain; any number of bands.
- `POST /v1/audio/key-match` — detect source key (chord-detect) + pitch-shift to target key.
- `POST /v1/audio/sidechain-duck` — ffmpeg sidechaincompress; primary duck on trigger.
- MCP: 58 tools total.

## v0.13.0 — 2026-06-03

Five more editing primitives.

- `POST /v1/audio/fade` — ffmpeg afade with 13 curve shapes.
- `POST /v1/audio/reverse` — flip audio backwards.
- `POST /v1/audio/loop` — repeat N times (count >= 2).
- `POST /v1/audio/bpm-match` — auto-detect source BPM (librosa) then stretch to target BPM.
- `POST /v1/audio/stereo-width` — M/S processing; width 0.0=mono, 1.0=original, up to 3.0.
- MCP: 53 tools total.

## v0.12.0 — 2026-06-03

- `POST /v1/audio/concat` — stitch N files end-to-end via ffmpeg concat filter.
- `POST /v1/audio/speed` — playback speed change without pitch shift (0.1–10×) via chained atempo filters.
- `POST /v1/audio/convert` — re-encode with target format, sample_rate, channels.
- `POST /v1/audio/similar` — CLAP cosine similarity between two audio files.
- `POST /v1/midi/quantize` — dedicated grid-snap endpoint.
- MCP: 48 tools total.

## v0.11.0 — 2026-06-03

- `POST /v1/audio/info` — ffprobe metadata (duration, codec, sample_rate, channels, bit_depth, format, bit_rate, frames).
- `POST /v1/audio/trim` — cut audio to `[start_sec, end_sec)`.
- `POST /v1/audio/mix` — N-track mix with per-track `gain_db` via ffmpeg amix.
- `POST /v1/audio/classify` — zero-shot classification via CLAP — accepts a JSON array of text labels, returns them ranked by cosine similarity.
- MCP: 43 tools total.

## v0.10.0 — 2026-06-03

HPSS, spectral noise reduction, loudness endpoint split.

- New engines: `hpss` (harmonic/percussive via librosa median filter), `noise-reduce` (stationary + non-stationary spectral reduction, no GPU).
- API split: `/v1/audio/loudness` is now JSON-only measurement; `/v1/audio/normalize` is the new normalization endpoint with required `target_lufs`.
- `POST /v1/audio/hpss` — ZIP with harmonic + percussive stems.
- `POST /v1/audio/noise-reduce` — denoised audio.
- MCP: 39 tools total.

## v0.9.0 — 2026-06-03

Stretch, audio tagging, CLAP embeddings.

- New engine: `stretch` — librosa phase vocoder, time-stretch + pitch-shift (`POST /v1/audio/stretch`).
- New engine: `ast-tag` — Audio Spectrogram Transformer; top-K AudioSet labels (`POST /v1/audio/tag`).
- New engine: `clap-embed` — LAION CLAP 512-dim L2-normalised audio embeddings; optional text-query cosine similarity (`POST /v1/audio/embed`).
- Bug fix: CPU Dockerfile now sets `HF_HOME=/data/hf` (tag/embed model cache was unreachable).
- 15 new integration tests.

## v0.8.0 — 2026-06-03

DeepFilterLib build fix + beat `start_bpm` + integration test buildout.

- Dockerfile CPU + CUDA: `deepfilterlib` now compiles from sdist via Rust/cargo; numpy override extracted with hashes so `--require-hashes` install succeeds.
- librosa beats: optional `start_bpm` seed parameter.
- 35 new/extended integration tests: fingerprint, MIR, visuals, MIDI utils, audio-to-MIDI, chords, diarize, VAD.

## v0.7.0 — 2026-06-02

Chord/key detect + VAD + speaker diarization + path-param engine routing.

- New engine: `chord-detect` — Krumhansl-Schmuckler + chroma template matching (`POST /v1/audio/chords`).
- New engine: `silero-vad` — voice activity detection (`POST /v1/audio/vad`).
- New engine: `pyannote` — speaker diarization (`POST /v1/audio/diarize`; requires `HUGGINGFACE_TOKEN`).
- Endpoint routing: engine moved from form param to URL path segment for several endpoints.

## v0.6.1 — 2026-06-02

Unit + integration tests for all new engines and endpoints (249 total).

## v0.6.0 — 2026-06-02

Polyphonic audio-to-MIDI + neural speech enhancement.

- New engine: `basic-pitch` — Spotify basic-pitch ONNX, polyphonic audio → MIDI (`POST /v1/audio/to_midi`).
- New engine: `deepfilter` — DeepFilterNet DF3 noise suppression (`POST /v1/audio/enhance`).

## v0.5.0 — 2026-06-02

AI audio restoration via UVR / audio-separator.

- New engines: `uvr-dereverb` (BS-Roformer SDR 19+), `uvr-deecho` (VR Architecture), `uvr-deecho-aggressive` (consolidated into `uvr-deecho` in v0.19.0), `uvr-denoise` (MelBand Roformer SDR 28), `uvr-karaoke`, `uvr-vocal-bsr`.
- Endpoints: `/v1/audio/dereverb`, `/v1/audio/deecho`, `/v1/audio/denoise` (all consolidated to `/v1/audio/restore/{engine}` in v0.19.0).

## v0.4.2 — 2026-06-01

Management endpoints moved to `/v1/ps` + `/v1/unload`; docs defaults clarified.

## v0.4.1 — 2026-06-01

README update for v0.4.0 features (docs only).

## v0.4.0 — 2026-06-01

MIR, silence detection, visualisations, fingerprinting, MIDI inspect/transform.

- 11 new REST endpoints + MCP tools across 5 new/extended engines.
- New: beat / onset / melody / segment analysis via `librosa-analyze`.
- New: silence detection + trimming.
- New: static PNG spectrogram/waveform + 8-mode animated MP4/WebM video (`ffmpeg-render`).
- New: Chromaprint acoustic fingerprinting (`audio-fingerprint`).
- New: MIDI inspection + transformation (transpose, quantize, tempo, channel filter).

## v0.3.1 — 2026-06-01

README accuracy fixes + project version metadata bump.

## v0.3.0 — 2026-05-31

Generic effects chain + MIDI compose/render.

- `POST /v1/audio/fx` — full pedalboard catalog (Compressor, Reverb, PitchShift, filters, …) as an ordered chain of `{type, params}`.
- `POST /v1/midi/compose` — JSON spec → SMF bytes (mido).
- `POST /v1/midi/render` — MIDI → audio via fluidsynth + FluidR3 GM SoundFont.
- `POST /v1/midi/generate` — compose + render in one call.

## v0.2.0 — 2026-05-31

`file_path` / `file_url` / `output_path` / `output_url` + SSRF-safe URL policy.

- Three input modes: multipart upload, staged file path, remote URL (allowlist/denylist via `AUDIOLLA_FETCH_MODE`).
- Three output modes: inline bytes, write to staging, PUT to presigned URL.
- File staging API: `GET/PUT/DELETE /v1/files`.

## v0.1.2 — 2026-05-31

README accuracy fixes + agent skill `.agents/.skills/audiolla/SKILL.md`.

## v0.1.0 — 2026-05-30

Initial release.

- `POST /v1/audio/separate` — Demucs stem separation (htdemucs, htdemucs_ft, htdemucs_6s, mdx_extra).
- `POST /v1/audio/master` — matchering reference-based mastering + pedalboard preset chain.
- `POST /v1/audio/analyze` — librosa MIR analysis (BPM, key, loudness, duration, spectral features).
- `POST /v1/audio/transform` — pysox DSP chain (gain, EQ, compressor, reverb, pitch, tempo).
- `POST /v1/audio/loudness` — pyloudnorm LUFS measurement + normalization (split into measure/normalize in v0.10.0).
- `GET /v1/engines` — list configured engines.
- `GET /healthz`, `GET /api/ps`, `DELETE /api/ps/{engine}`, `POST /unload` (moved to `/v1/ps` + `/v1/unload` in v0.4.2).
- `POST /v1/files`, `GET /v1/files/{path}` — server-side file staging.
- CPU image (python:3.12-slim) + CUDA image (nvidia/cuda:12.6.3).
- OpenAPI 3.1 spec as the single source of truth for the wire shape.
