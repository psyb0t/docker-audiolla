# AGENTS.md

Guide for coding agents working on this repository. If you only want to call a running audiolla server from an agent, read [.agents/skills/audiolla/SKILL.md](.agents/skills/audiolla/SKILL.md) instead; this file is about changing the code.

The project rules live in `.agents/rules/`, one file per topic. They are authoritative for this repository.

## Agent setup

`CLAUDE.md` is a committed symlink to `AGENTS.md`, and `.claude` is a committed symlink to `.agents`, so Claude Code reads the same instructions, rules and skills as Codex. Claude's Edit and Write tools refuse to write through a symlink: edit `AGENTS.md` and `.agents/rules/*.md` directly, never the paths under `CLAUDE.md` or `.claude/`.

## What it is

audiolla is a self-hosted audio production API in one Docker image: stem separation, restoration, mastering, effects, MIR analysis, speech tools, MIDI transcription, composition and rendering, and text-to-audio generation, behind 94 REST routes and an 82-tool MCP endpoint on port 8000.

It wraps many open-source audio tools (Demucs, UVR through audio-separator, matchering, pedalboard, librosa, SoX, ffmpeg, basic-pitch, DeepFilterNet, silero-vad, pyannote, AST, CLAP, fluidsynth, diffusers and transformers generators) behind one JSON API, loads models lazily, unloads them when idle, and ships as a CPU image and a CUDA image. The user documentation is the GitHub Pages site built from `docs/`.

## Architecture

- **One FastAPI process.** `src/audiolla/server.py` builds the app, every REST route, the middleware stack, the idle-engine, job and file sweepers, the `/v1/catalog` table and the MCP mount. `python -m audiolla` (`src/audiolla/__main__.py`) configures logging and runs uvicorn on `0.0.0.0:8000`.
- **Spec-first API.** `openapi.yaml` is the REST contract. `make generate` turns it into Pydantic models in `src/audiolla/schema/_generated.py`; `src/audiolla/schema/__init__.py` re-exports them and holds the either-or validators. The server serves `openapi.yaml` itself at `/openapi.json` (`_openapi_override`). See `.agents/rules/api-contract.md`.
- **Configuration at import.** `src/audiolla/config.py` reads every `AUDIOLLA_*` variable when imported and raises `ValueError` on a bad value. `load_registry()` reads the engine registry (`AUDIOLLA_ENGINES_FILE`, default `/app/engines.json`), validates executors against `_VALID_EXECUTORS` and applies `AUDIOLLA_ENABLED_ENGINES`.
- **Engines.** `engines.json` (CUDA image, 35 slugs) and `engines-cpu.json` (CPU image, 27 slugs) map a slug to an `executor` and its fields. `build_engines()` in `src/audiolla/engines/__init__.py` builds one object per slug; every engine extends `EngineBase` (`src/audiolla/engines/base.py`: lazy `get_model()`, per-engine lock, `unload(if_idle_for=...)`). Capability is duck-typed with the `is_*_engine()` predicates. Stateless DSP lives in `src/audiolla/audio.py` and needs no engine.
- **Request flow.** Handlers validate the generated body model, call `validate_input_xor` / `validate_output_xor`, read input through `resolve_input` (`src/audiolla/input_resolver.py`: staged path or fetched URL), run the engine or `audio.py` function, and route the result through `_run_with_optional_job` to `write_output` (`src/audiolla/output_writer.py`: staging, `PUT` to `output_url`, or a background job).
- **Staging and retention.** `src/audiolla/files.py` sanitizes paths and keeps them under `/data/files`. `src/audiolla/file_retention.py` deletes files older than `AUDIOLLA_FILES_TTL`; every `/v1/` request and job holds a shared `flock` on `/data/.files-cleanup.lock` and the sweep needs it exclusively, which also coordinates containers sharing `/data`.
- **Outbound URLs.** `src/audiolla/fetch.py` applies `AUDIOLLA_FETCH_MODE` (default `disabled`), host lists, scheme list, private-address checks, manual redirects and the size cap to `file_url` and `output_url`.
- **Jobs.** `src/audiolla/jobs.py` keeps an in-memory `JOB_QUEUE`; `async_job: true` returns 202 with `job_id`, and completed jobs `POST` to `webhook_url`.
- **Presets and pipelines.** `src/audiolla/pipeline.py` holds the 24-op table used by `/v1/pipeline`, `/v1/presets/{name}` and their MCP tools; `src/audiolla/presets.py` loads `presets/*.yaml` from `AUDIOLLA_PRESETS_DIR`.
- **MCP.** `src/audiolla/mcp_server.py` builds a stateless FastMCP server (`build_mcp_server(engines=..., registry=..., presets=...)`) with 82 tools, mounted at `/v1/mcp`.
- **Auth.** `BearerAuthMiddleware` (`src/audiolla/auth.py`) checks one optional token (`AUDIOLLA_AUTH_TOKEN`) for every route including `/v1/mcp`; `/healthz` and `OPTIONS` are exempt.
- **Entrypoint.** `entrypoint.sh` mirrors `HF_TOKEN` and `HUGGINGFACE_TOKEN`, creates `/data` directories, validates `AUDIOLLA_ENABLED_ENGINES`, downloads the checkpoint of each enabled Demucs engine (`prefetch: "demucs"`) into `TORCH_HOME=/data/torch_cache`, then `exec`s the server. Other engines download weights on first use.
- **Agent integrations.** `.agents/skills/audiolla/` is the agent skill; `.agents/plugins/audiolla/` is the OpenClaw plugin, a Node launcher for `mcp-remote` against `$AUDIOLLA_URL/v1/mcp`; `.agents/.claude-plugin/` and `.agents/.codex-plugin/` hold the plugin manifests; `server.json` is the MCP Registry entry; `glama.json` is the Glama maintainer claim.

Data flow:

```text
engines.json / engines-cpu.json + AUDIOLLA_ENABLED_ENGINES
  -> entrypoint.sh (Demucs prefetch) -> server.py import: load_registry() -> build_engines()

client -> MCP slash rewrite -> request log -> bearer auth -> retention lease -> route
  REST: generated model -> validate_*_xor -> resolve_input (staging | file_url)
        -> engine / audio.py -> _run_with_optional_job -> write_output (staging | output_url | job)
  /v1/mcp (FastMCP): tools call the same engines and audio.py functions
```

## Stack

- Language: Python 3.12 in every image (`requires-python = ">=3.10,<3.13"` in `pyproject.toml`).
- Framework: FastAPI and uvicorn, pydantic v2, the `mcp` SDK (FastMCP), httpx, mido, mutagen.
- ML and DSP: Torch 2.5.1 with torchaudio, Demucs, audio-separator (UVR), matchering, pedalboard, librosa, pyloudnorm, pysox, noisereduce, DeepFilterNet, basic-pitch (ONNX), silero-vad, pyannote.audio, transformers and diffusers. System tools: ffmpeg, sox, fluidsynth with FluidR3_GM, chromaprint `fpcalc`.
- Packaging: hatchling; light dependencies in `uv.lock`, the ML stack in hash-locked `requirements-heavy-cpu.txt` and `requirements-heavy-cuda.txt`.
- Deploy: `psyb0t/audiolla:<tag>` (CPU, `Dockerfile`) and `psyb0t/audiolla:<tag>-cuda` (`Dockerfile.cuda`), both `linux/amd64`, built on Torchbase images pinned by digest. No compose file ships.
- CI: GitHub Actions through `psyb0t/reusable-github-workflows` at `@master`.

## Layout

| Path | What it owns |
| --- | --- |
| `src/audiolla/server.py` | FastAPI app, all REST routes, middleware, sweepers, `_CATALOG_GROUPS`, `_evict_siblings`, `_run_with_optional_job`, MCP mount. |
| `src/audiolla/mcp_server.py` | FastMCP server and its 82 tools. |
| `src/audiolla/schema/_generated.py` | Generated from `openapi.yaml` by `make generate`. Never hand-edit. |
| `src/audiolla/schema/__init__.py` | Hand-written re-export layer, alias-to-subclass fixups, `validate_input_xor`, `validate_multi_input_xor`, `validate_output_xor`, `url_to_str`, `format_value`. |
| `src/audiolla/config.py` | All `AUDIOLLA_*` settings parsed at import, `_VALID_EXECUTORS`, `load_registry()`. |
| `src/audiolla/engines/` | One module per executor, `base.py` (`EngineBase`), the factory and `is_*_engine()` predicates in `__init__.py`. |
| `src/audiolla/audio.py` | Stateless DSP functions, `AudioConversionError`, `SUPPORTED_OUTPUT_FORMATS`. |
| `src/audiolla/input_resolver.py`, `output_writer.py` | Input resolution and output routing. |
| `src/audiolla/files.py`, `file_retention.py` | Staging path safety, atomic writes, retention sweep and leases. |
| `src/audiolla/fetch.py` | SSRF-guarded fetch and upload. |
| `src/audiolla/jobs.py` | In-memory job queue and webhooks. |
| `src/audiolla/pipeline.py`, `presets.py` | Pipeline op table and preset loader. |
| `src/audiolla/auth.py`, `logging.py` | Bearer middleware; JSON logging with request correlation. |
| `openapi.yaml` | The REST contract, also copied into the images and served at `/openapi.json`. |
| `engines.json`, `engines-cpu.json` | Engine registries for the CUDA and CPU images. |
| `presets/` | Shipped preset YAML files. |
| `entrypoint.sh` | Token mirroring, data directories, Demucs prefetch, server start. |
| `Dockerfile`, `Dockerfile.cuda`, `Dockerfile.dev` | CPU image, CUDA image, light dev image the Makefile runs tools in. |
| `pyproject.toml`, `uv.lock` | Metadata, the canonical version, light runtime dependencies, the uv `exclude-newer` age gate, mypy settings. |
| `requirements-heavy-*.txt`, `scripts/heavy-deps-*.in`, `scripts/heavy-deps-overrides.txt` | Generated hash-locked ML stacks and their inputs. |
| `scripts/` | `generate_models.sh`, `compile_heavy_deps.sh`, `bump_exclude_newer.sh`. Excluded from the Docker build context. |
| `tests/` | Offline unit tests (`test_*.py`), `image_smoke.py`, and `tests/integration/` (pytest against a real container). |
| `docs/` | GitHub Pages documentation site (Just the Docs). `README.md` links to it. |
| `.agents/` | Skill, OpenClaw plugin, Claude and Codex plugin manifests, and these rules. Excluded from the Docker build context. |
| `.github/workflows/` | `pipeline.yml` (lint, tests, images, badges, release, ClawHub and MCP Registry), `collaborators-only.yml`, `mirror-and-archive.yml`, `issue-pull.yml`. |
| `server.json`, `glama.json` | MCP Registry entry and Glama claim. |
| `THIRD_PARTY.md`, `LICENSES/` | Third-party components in the images and their license texts. |

## Dev workflow

Every tool runs in the dev container (`Dockerfile.dev`, tag `psyb0t/audiolla-dev:latest`) with the repository mounted at `/work`, except image builds, `test-image` and the integration tests. `make help` lists all targets.

| Target | What it does |
| --- | --- |
| `make dev-image` | Builds the dev image (Python 3.12, uv, flake8, black, isort, mypy, pytest, the light web stack, datamodel-code-generator; no ML stack). Dev targets depend on it. |
| `make shell` | Interactive shell in the dev container. |
| `make lint` | `flake8 src`, then `mypy src`. |
| `make format` | `isort src`, then `black src`. |
| `make test`, `make test-unit` | `pytest tests/ --ignore=tests/integration` with coverage. Offline, no GPU. |
| `make test-unit-cov-gate` | Unit tests with an 80% gate on the support modules. |
| `make test-retention` | Retention and config tests with a 90% gate on `file_retention`. |
| `make check` | `lint`, then `test`. |
| `make generate` | Regenerates `src/audiolla/schema/_generated.py` from `openapi.yaml`. |
| `make build`, `make build-cuda`, `make build-all` | Builds the images, tagged `local`, `v<version>` and `latest` (`-cuda` suffix). |
| `make run`, `make run-cuda` | Builds and runs the image on `PORT` (default 8000) with `~/.audiolla-data` as `/data`. |
| `make test-image` | Runs `tests/image_smoke.py` in the built CPU image (`DEVICE=cuda` for the CUDA image). |
| `make test-integration` | `pytest tests/integration/` on the host; builds the CPU image unless `HARNESS_SKIP_BUILD=1` and spawns one container. |
| `make pkg-add PKG=...`, `pkg-remove`, `pkg-update`, `pkg-upgrade` | Move `exclude-newer` to UTC midnight seven days ago, then change dependencies through uv. |
| `make pkg-lock` | `uv lock` at the current cutoff. |
| `make pkg-compile-heavy` | Recompiles `requirements-heavy-*.txt` (`VARIANT=cpu`, `cuda` or `all`). |
| `make docs` | Builds `docs/` with the GitHub Pages Jekyll image into `.testing/docs-site`. |
| `make version` | Prints `v` plus the `pyproject.toml` version. |
| `make clean` | Removes local images and build and cache artifacts. |

## Project-specific landmines

- **CI regenerates the schema.** The `code` job runs `make lint`, `make test` and `make generate`, and fails if generation changes any file. Commit `openapi.yaml` and `src/audiolla/schema/_generated.py` together (API6, API12).
- **The two registries differ.** `htdemucs_ft`, `htdemucs_6s`, `mdx_extra` and the five generators exist only in `engines.json` (CUDA). A request for a slug the running registry lacks gets 404, not the `cuda_only` 400.
- **A missing engine is a 404.** Handlers do `ENGINES.get("<slug>")` and answer 404 `"<slug> engine not configured"`. `_require_engine()` (503) in `server.py` is never called.
- **`server.py` has no `from __future__ import annotations` on purpose.** PEP 563 strings broke FastAPI's body detection for the generated models in v1.0.0 (comment at the top of `server.py`). Every other module has it.
- **Some routes still bypass the contract.** `/v1/midi/compose`, `/v1/midi/generate` and `/v1/midi/drum` read a raw JSON body and take outputs from query parameters with `Form()` defaults, and return inline bytes when no output is given. See API1 to API4 for what the spec-first rule requires of new work.
- **Spec and code disagree in places.** `POST /v1/batch` returns `{"results": [...]}` while the spec says an array; job records use `id` while the spec says `job_id`; the remix `stem_mix` description says linear while the handler treats values above 1 as dB; VAD and diarize list a 202 they cannot return. Fix the code or the spec in the same change when you touch one of them (API1).
- **`async_job` is ignored by some handlers.** `/v1/midi/render`, `/v1/midi/transform`, `/v1/midi/quantize`, `/v1/midi/humanize` and `/v1/audio/chords-to-midi` accept the field but call `write_output` directly.
- **Five MCP tools skip the fetch policy.** `audio_thumbnail`, `chords_to_midi`, `deess`, `drum_pattern` and `midi_humanize` `PUT` to `output_url` with a bare `httpx.AsyncClient` (SEC5). Webhook URLs are not policy-checked either.
- **`AUDIOLLA_LOAD_TIMEOUT` and `AUDIOLLA_JOB_MAX_CONCURRENT` are parsed but never enforced.**
- **Model weights never enter git or the image.** `.gitignore` and `.dockerignore` exclude `*.safetensors`, `*.ckpt`, `*.pt`, `*.pth`, `*.onnx`, `*.bin` and the rest; weights reach a container only at startup or first use.
- **The Docker build context excludes** `docs/`, `tests/`, `scripts/`, `.agents/`, `README.md`, `CHANGELOG.md`, `Makefile` and `Dockerfile.dev` (`.dockerignore`). Nothing there can be `COPY`ed into an image.
- **`.e2e-cache/`** holds multi-GB model snapshots for the integration suite. It is gitignored and excluded from the build context; never commit or `COPY` it.
- **Untracked local state.** `.research_files/`, `.testing/`, `.telemetry/`, `.agent_notes/`, `TODO.md`, `.coverage` and `git-update.sh` are local and gitignored; `git-update.sh` is the maintainer's release script, not part of the project.
- **Outside pull requests are closed automatically** by `collaborators-only.yml`. Issues from the GitLab and Codeberg mirrors are pulled in by `issue-pull.yml`.

## Common changes

Adding or changing a REST endpoint: follow API1 to API7 in [api-contract.md](.agents/rules/api-contract.md): `openapi.yaml` first, `make generate`, then the handler in `server.py`. Add it to `_CATALOG_GROUPS`, write unit tests (TST2), and update the docs page, `docs/api.md` (DOC2) and the CHANGELOG.

Adding an engine with an existing executor:

1. Add the entry to `engines.json`, and to `engines-cpu.json` if it runs on CPU (ENG1, ENG2).
2. Update `docs/engines.md`, the feature page and the README counts (DOC2).

Adding an executor: write the module in `src/audiolla/engines/`, add the name to `_VALID_EXECUTORS` in `config.py` and a branch in `build_engines()` (ENG3, ENG4), add a predicate if the capability is new, and unit-test it without the ML stack (TST3).

Adding a setting: read it in `config.py` with the existing parsers (PY4, PY5), add it to `.env.example` and `docs/configuration.md` (DOC2), and test it in `tests/test_config.py` (TST4).

Adding an MCP tool: [mcp.md](.agents/rules/mcp.md).

Releasing: [docs-and-releases.md](.agents/rules/docs-and-releases.md).

## Rules

Rules for every change: `.agents/rules/`. Read the area file before touching that area:

| File | Read before touching |
| --- | --- |
| `api-contract.md` | `openapi.yaml`, `src/audiolla/schema/`, REST routes in `src/audiolla/server.py`, `scripts/generate_models.sh` |
| `python-code.md` | Any `src/audiolla/*.py`, `pyproject.toml`, `.flake8` |
| `engines.md` | `src/audiolla/engines/`, `engines.json`, `engines-cpu.json`, `entrypoint.sh`, the Dockerfiles, `requirements-heavy-*.txt`, `scripts/heavy-deps-*.in`, `uv.lock` |
| `mcp.md` | `src/audiolla/mcp_server.py`, the `/v1/mcp` mount, `.agents/plugins/audiolla/`, `server.json` |
| `security.md` | `auth.py`, `files.py`, `file_retention.py`, `fetch.py`, `input_resolver.py`, `output_writer.py`, `jobs.py`, `logging.py`, the Dockerfiles, `.github/workflows/`, `.gitleaks.toml`, `THIRD_PARTY.md` |
| `testing.md` | `tests/`, `tests/integration/` |
| `docs-and-releases.md` | `README.md`, `docs/`, `CHANGELOG.md`, `.agents/skills/`, any version field, release tags |
