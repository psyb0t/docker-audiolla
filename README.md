# audiolla

[![Docker Pulls](https://img.shields.io/docker/pulls/psyb0t/audiolla?style=flat-square)](https://hub.docker.com/r/psyb0t/audiolla)
[![Docker Hub](https://img.shields.io/docker/v/psyb0t/audiolla?sort=semver&label=Docker%20Hub&style=flat-square)](https://hub.docker.com/r/psyb0t/audiolla)
[![License: WTFPL](https://img.shields.io/badge/License-WTFPL-brightgreen.svg?style=flat-square)](http://www.wtfpl.net/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg?style=flat-square)](https://www.python.org/downloads/)

> POST a track. Get stems, a master, analysis, or a processed file back. No cloud, no accounts, runs wherever Docker runs.

HTTP API + MCP server for audio processing. You throw a WAV (or MP3, FLAC, whatever) at an endpoint and get audio or JSON out. Split a track into stems with Demucs. Master against a reference with matchering. Measure LUFS. Run a pedalboard effect chain. Extract BPM and key with librosa. Chain sox transforms. All from curl, any HTTP client, or an LLM agent over MCP.

Engines lazy-load on first use and auto-unload after idle. CPU and CUDA images. OpenAPI spec included.

---

## Table of Contents

- [Run it](#run-it)
- [What it can do](#what-it-can-do)
  - [Split stems](#split-stems)
  - [Master](#master)
  - [Analyze](#analyze)
  - [Transform](#transform)
  - [Loudness](#loudness)
  - [Stage files](#stage-files)
- [Engines](#engines)
- [Endpoints](#endpoints)
- [MCP](#mcp)
- [Configuration](#configuration)
- [What's not in here](#whats-not-in-here)
- [Build & dev](#build--dev)
- [Supply chain](#supply-chain)
- [License](#license)

---

## Run it

```bash
# no GPU
docker run --rm -it \
  -v $HOME/.audiolla-data:/data \
  -p 8000:8000 \
  psyb0t/audiolla:latest

# GPU
docker run --rm -it --gpus all \
  -v $HOME/.audiolla-data:/data \
  -e AUDIOLLA_DEVICE=cuda \
  -p 8000:8000 \
  psyb0t/audiolla:latest-cuda
```

Demucs weights download on first use and cache in `/data/torch_cache/` — same `-v` mount next time and they're already there.

---

## What it can do

Output defaults to `wav`. Any endpoint that returns audio accepts `-F "output_format=mp3"` (also `flac`, `opus`, `aac`, `pcm`).

### Split stems

```bash
# vocals only
curl -X POST http://localhost:8000/v1/audio/separate \
  -F "file=@track.wav" \
  -F "engine=htdemucs" \
  -F "stems=vocals" \
  -o vocals.wav

# all 4 stems as a ZIP
curl -X POST http://localhost:8000/v1/audio/separate \
  -F "file=@track.wav" \
  -F "engine=htdemucs" \
  -o stems.zip
```

### Master

```bash
# match EQ + loudness to a reference track
curl -X POST http://localhost:8000/v1/audio/master \
  -F "file=@track.wav" \
  -F "mode=reference" \
  -F "reference=@ref.wav" \
  -o mastered.wav

# run a built-in pedalboard chain (presets: transparent, loud)
curl -X POST http://localhost:8000/v1/audio/master \
  -F "file=@track.wav" \
  -F "mode=chain" \
  -F "preset=loud" \
  -o mastered.wav
```

### Analyze

```bash
# returns JSON. features: bpm, key, loudness, duration,
# spectral_centroid, rms, zcr. Omit features= to get them all.
curl -X POST http://localhost:8000/v1/audio/analyze \
  -F "file=@track.wav" \
  -F "features=bpm" \
  -F "features=key" \
  -F "features=loudness"
```

### Transform

```bash
# pitch shift up 2 semitones + add reverb, export mp3.
# operations is a JSON array — ops: gain, equalizer, compand, reverb,
# pitch, tempo, rate, channels, trim, pad.
curl -X POST http://localhost:8000/v1/audio/transform \
  -F "file=@track.wav" \
  -F 'operations=[{"op":"pitch","params":{"n_semitones":2}},{"op":"reverb","params":{"reverberance":50}}]' \
  -F "output_format=mp3" \
  -o out.mp3
```

### Loudness

```bash
# measure integrated LUFS (returns JSON)
curl -X POST http://localhost:8000/v1/audio/loudness \
  -F "file=@track.wav"

# normalize to -14 LUFS and get the file back
curl -X POST http://localhost:8000/v1/audio/loudness \
  -F "file=@track.wav" \
  -F "target_lufs=-14" \
  -o normalized.wav
```

### Stage files

A simple server-side file store under `/v1/files`. Upload, list, download, delete.

```bash
# upload
curl -X PUT http://localhost:8000/v1/files/mytrack.wav \
  --data-binary @track.wav

# list
curl http://localhost:8000/v1/files

# download
curl http://localhost:8000/v1/files/mytrack.wav -o copy.wav

# delete
curl -X DELETE http://localhost:8000/v1/files/mytrack.wav
```

Use it to keep big files on the server, share input/output between clients, or feed staged paths to MCP tools (`put_file` / `separate file_path=...` etc.). The REST audio endpoints take the file inline — they don't reference staged paths.

---

## Engines

| Slug | What it does |
|------|--------------|
| `htdemucs` | 4-stem separation: drums, bass, other, vocals. Best speed/quality tradeoff. |
| `htdemucs_ft` | Same 4 stems, fine-tuned weights. Higher quality, ~4x slower. |
| `htdemucs_6s` | 6 stems — also splits guitar and piano. Experimental. |
| `mdx_extra` | Strong on vocal isolation. MUSDB-trained, different architecture. |
| `matchering` | Reference-based mastering: EQ + loudness matched to a reference track. |
| `pedalboard-chain` | Fixed DSP chain via pedalboard: compression, EQ, limiting. |
| `librosa-analyze` | BPM, key, LUFS, duration, spectral features via librosa. |
| `sox-transform` | Gain, EQ, compression, reverb, pitch shift, tempo via pysox. |

Demucs variants all pull from the same `facebook/demucs` checkpoint. Weights get prefetched into `/data/torch_cache/` at startup so your first separation request doesn't sit there downloading.

`AUDIOLLA_ENABLED_ENGINES` — restrict which engines are available. `AUDIOLLA_PRELOAD` — load specific engines into memory at startup instead of waiting for the first request.

---

## Endpoints

Full wire contract: [`openapi.yaml`](openapi.yaml).

### Audio processing

| Method | Path | Returns |
|--------|------|---------|
| `POST` | `/v1/audio/separate` | ZIP (multiple stems) or audio bytes (single stem) |
| `POST` | `/v1/audio/master` | audio bytes |
| `POST` | `/v1/audio/analyze` | JSON |
| `POST` | `/v1/audio/transform` | audio bytes |
| `POST` | `/v1/audio/loudness` | JSON (no `target_lufs`) or audio bytes (with `target_lufs`) |

### File staging

| Method | Path | |
|--------|------|-|
| `GET` | `/v1/files` | list staged files |
| `PUT` | `/v1/files/{path}` | upload |
| `GET` | `/v1/files/{path}` | download |
| `DELETE` | `/v1/files/{path}` | delete |

### Management

| Method | Path | |
|--------|------|-|
| `GET` | `/healthz` | liveness — always unauthenticated |
| `GET` | `/v1/engines` | list configured engines |
| `GET` | `/api/ps` | list engines in memory right now |
| `DELETE` | `/api/ps/{engine}` | evict one engine |
| `POST` | `/unload` | evict everything |

---

## MCP

audiolla exposes a [Model Context Protocol](https://modelcontextprotocol.io) server at `/v1/mcp` using the streamable HTTP transport. Point any MCP client there and an LLM agent can drive the full audio processing surface — separate stems, master tracks, analyze, transform, normalize — without touching the REST API directly.

Audio in and out over MCP is base64-encoded (JSON-RPC can't carry raw bytes). The intended workflow is: `put_file` to stage a file, call whatever tools you need, `get_file` to pull results back.

**Endpoint:** `http://localhost:8000/v1/mcp`

**Tools:**

| Tool | What it does |
|------|--------------|
| `list_engines` | List configured engines and whether they're loaded |
| `separate` | Demucs stem separation on a staged file — returns base64 stems |
| `master` | Reference mastering (matchering) or preset chain (pedalboard) |
| `analyze` | BPM, key, LUFS, spectral features via librosa |
| `transform` | Sox DSP chain — gain, EQ, reverb, pitch, tempo, etc. |
| `loudness` | Measure LUFS or normalize to a target |
| `list_files` | List staged files |
| `put_file` | Upload a file (base64) to the staging area |
| `get_file` | Read a staged file back (base64) |
| `delete_file` | Remove a staged file |

Auth (`AUDIOLLA_AUTH_TOKEN`) covers `/v1/mcp` the same as the REST endpoints — pass the bearer token in the `Authorization` header.

---

## Configuration

| Variable | Default | |
|----------|---------|-|
| `AUDIOLLA_DEVICE` | `auto` | `auto`, `cpu`, `cuda`, or `cuda:N` |
| `AUDIOLLA_ENGINES_FILE` | `/app/engines.json` | path to engines registry |
| `AUDIOLLA_DATA_DIR` | `/data` | where models and staged files live |
| `AUDIOLLA_AUTH_TOKEN` | — | bearer token; empty means no auth |
| `AUDIOLLA_ENABLED_ENGINES` | _(all)_ | comma-separated slugs to allow; empty = all |
| `AUDIOLLA_PRELOAD` | — | comma-separated slugs to load at startup |
| `AUDIOLLA_ENGINE_TTL` | `600` | seconds idle before an engine is unloaded (`10m` also works) |
| `AUDIOLLA_SWEEPER_INTERVAL` | `60` | how often the idle sweeper checks, in seconds |
| `AUDIOLLA_MAX_UPLOAD_BYTES` | `209715200` | upload cap (200 MB) |

---

## What's not in here

| | Why |
|-|-----|
| Music generation | MusicGen is CC-BY-NC. Stable Audio Open needs a Stability AI commercial agreement. Nothing permissively licensed at production quality exists yet. |
| Essentia analysis | AGPL v3 — any network service using it has to publish full source. librosa handles the common cases without that. |
| Streaming separation | Demucs needs the whole file. No chunked or real-time inference. |
| Speech denoising | resemble-enhance / DeepFilterNet are for speech. Useful after you've already pulled vocals with Demucs, but that's a different tool. |
| VST3 plugin hosting | Pedalboard can do it but you'd need to mount your host plugin directory. Out of scope for the default image. |
| rubberband pitch/time-stretch | GPL v2 + commercial license. Sox handles basic pitch and tempo. Add it yourself if you accept the terms. |

---

## Build & dev

```bash
make build        # CPU image
make build-cuda   # CUDA image
make run          # CPU image on port 8000
make run-cuda     # CUDA image on port 8000
```

```bash
make dev-image          # build the dev container
make shell              # shell inside it
make lint               # flake8 + mypy
make format             # isort + black
make test-unit          # unit tests (no GPU, no ML deps needed)
make test-unit-cov-gate # fail if coverage on support modules drops below 80%
make test-integration   # integration tests (spins up Docker containers)
make generate           # regenerate src/audiolla/schema/ from openapi.yaml
make clean              # wipe build/cache artifacts
```

```bash
make pkg-lock                 # refresh uv.lock
make pkg-add PKG=name[==ver]  # add a dep
make pkg-update PKG=name      # upgrade one dep
make pkg-upgrade              # upgrade everything
make pkg-remove PKG=name      # remove a dep
make pkg-compile-heavy        # recompile requirements-heavy-{cpu,cuda}.txt
```

Every `make pkg-*` bumps `[tool.uv] exclude-newer` to today's UTC midnight before touching anything — packages younger than the gate are refused. Everything runs inside the dev container. Host needs `docker`, `make`, `git`.

---

## Supply chain

Both prod images do a two-layer install.

**Light deps** (`fastapi`, `uvicorn`, `pydantic`, etc.): locked in `uv.lock`, installed with `uv sync --frozen --no-dev`. Build fails if the lockfile doesn't match `pyproject.toml`. Wheel hashes verified by uv.

**Heavy ML/DSP deps** (torch, demucs, matchering, pedalboard, librosa, sox, numpy, soundfile, huggingface-hub): one hash-locked requirements file per image variant (`requirements-heavy-cpu.txt`, `requirements-heavy-cuda.txt`), because the torch wheel differs between CPU and CUDA and lives on a different index. Human specs in `scripts/heavy-deps-{cpu,cuda}.in`, compiled via `make pkg-compile-heavy`, installed with `uv pip install --require-hashes`. Both files are committed.

Base images and the `uv` binary pinned by `@sha256:` digest.

---

## License

[WTFPL](LICENSE).

matchering and pedalboard are GPL v3. Fine for self-hosted use. Distributing the image as a product needs a GPL compliance review.
