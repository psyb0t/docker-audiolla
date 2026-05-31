# audiolla

[![Docker Pulls](https://img.shields.io/docker/pulls/psyb0t/audiolla?style=flat-square)](https://hub.docker.com/r/psyb0t/audiolla)
[![Docker Hub](https://img.shields.io/docker/v/psyb0t/audiolla?sort=semver&label=Docker%20Hub&style=flat-square)](https://hub.docker.com/r/psyb0t/audiolla)
[![License: WTFPL](https://img.shields.io/badge/License-WTFPL-brightgreen.svg?style=flat-square)](http://www.wtfpl.net/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg?style=flat-square)](https://www.python.org/downloads/)

> **Self-hosted music-production API.** Stem separation, mastering, MIR analysis, DSP transforms, loudness normalization — one Docker container, one wire format.

---

## Table of Contents

- [Quick Start](#quick-start)
- [Usage](#usage)
- [Engines](#engines)
- [Endpoints](#endpoints)
- [Configuration](#configuration)
- [What's Not Included](#whats-not-included)
- [Build & Development](#build--development)
- [Supply Chain](#supply-chain)
- [License](#license)

---

## Quick Start

```bash
# CPU (no GPU needed)
docker run --rm -it \
  -v $HOME/.audiolla-data:/data \
  -p 8000:8000 \
  psyb0t/audiolla:latest

# CUDA (GPU-accelerated Demucs)
docker run --rm -it --gpus all \
  -v $HOME/.audiolla-data:/data \
  -e AUDIOLLA_DEVICE=cuda \
  -p 8000:8000 \
  psyb0t/audiolla:latest-cuda
```

Demucs model weights download on first run and cache in `/data/torch_cache/`.
Same `-v` mount on next run skips the download.

---

## Usage

Output format defaults to `wav`. Add `-F "output_format=mp3"` (or `flac`, `opus`, `aac`, `pcm`) to any request that returns audio.

### Stem separation

```bash
# Pull vocals out of a track
curl -X POST http://localhost:8000/v1/audio/separate \
  -F "file=@track.wav" \
  -F "engine=htdemucs" \
  -F "stems=vocals" \
  -o vocals.wav

# Get all 4 stems as a ZIP
curl -X POST http://localhost:8000/v1/audio/separate \
  -F "file=@track.wav" \
  -F "engine=htdemucs" \
  -o stems.zip
```

### Mastering

```bash
# Match loudness + EQ against a reference track
curl -X POST http://localhost:8000/v1/audio/master \
  -F "file=@track.wav" \
  -F "mode=reference" \
  -F "reference=@ref.wav" \
  -o mastered.wav

# Run the built-in pedalboard DSP chain
curl -X POST http://localhost:8000/v1/audio/master \
  -F "file=@track.wav" \
  -F "mode=chain" \
  -o mastered.wav
```

### MIR analysis

```bash
# Get BPM, key, LUFS, duration, spectral features
curl -X POST http://localhost:8000/v1/audio/analyze \
  -F "file=@track.wav" \
  -F "features=bpm" \
  -F "features=key" \
  -F "features=lufs"
```

### DSP transforms

```bash
# Compress + add reverb, export as mp3
curl -X POST http://localhost:8000/v1/audio/transform \
  -F "file=@track.wav" \
  -F "effects=compand" \
  -F "effects=reverb" \
  -F "output_format=mp3" \
  -o out.mp3
```

### Loudness

```bash
# Measure LUFS (returns JSON)
curl -X POST http://localhost:8000/v1/audio/loudness \
  -F "file=@track.wav"

# Normalize to -14 LUFS (streaming target)
curl -X POST http://localhost:8000/v1/audio/loudness \
  -F "file=@track.wav" \
  -F "target_lufs=-14" \
  -o normalized.wav
```

### File staging

Stage files server-side for large uploads or multi-step pipelines instead of uploading the same file repeatedly.

```bash
# Upload once
curl -X PUT http://localhost:8000/v1/files/mytrack.wav \
  --data-binary @track.wav

# Reference by path in subsequent requests
curl -X POST http://localhost:8000/v1/audio/analyze \
  -F "file_path=mytrack.wav" \
  -F "features=bpm"

# Clean up
curl -X DELETE http://localhost:8000/v1/files/mytrack.wav
```

---

## Engines

| Slug | Backend | What it does |
|------|---------|--------------|
| `htdemucs` | demucs | 4-stem separation (drums / bass / other / vocals). Best speed/quality balance. |
| `htdemucs_ft` | demucs | Same 4 stems, fine-tuned. Highest quality, ~4x slower. |
| `htdemucs_6s` | demucs | 6 stems — adds guitar and piano. Experimental. |
| `mdx_extra` | demucs | Strong vocal isolation. MUSDB-trained. |
| `matchering` | matchering | Reference-based mastering — EQ + loudness matched to a reference track. |
| `pedalboard-chain` | pedalboard | Preset DSP chain: compression, EQ, limiting. Transparent and loud. |
| `librosa-analyze` | librosa | MIR analysis: BPM, key, LUFS, duration, spectral features. |
| `sox-transform` | pysox | DSP transform chain: gain, EQ, compressor, reverb, pitch, tempo. |

All Demucs variants share the `facebook/demucs` HuggingFace checkpoint. The entrypoint prefetches them into `/data/torch_cache/` at startup so the first request doesn't pay the cold-download cost.

Use `AUDIOLLA_ENABLED_ENGINES` to activate only the engines you need. Use `AUDIOLLA_PRELOAD` to warm specific engines into memory at startup instead of on first request.

---

## Endpoints

Full wire contract: [`openapi.yaml`](openapi.yaml).

### Audio

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/v1/audio/separate` | Stem separation via Demucs. Returns ZIP for multiple stems, audio bytes for a single stem. |
| `POST` | `/v1/audio/master` | Mastering. `mode=reference` → matchering; `mode=chain` → pedalboard preset. |
| `POST` | `/v1/audio/analyze` | MIR analysis via librosa. Returns JSON. |
| `POST` | `/v1/audio/transform` | DSP transform chain via pysox. Returns audio bytes. |
| `POST` | `/v1/audio/loudness` | No `target_lufs` → LUFS measurement (JSON). With `target_lufs` → normalized audio bytes. |

Output formats: `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm`.

### File staging

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/v1/files` | List staged files. |
| `PUT` | `/v1/files/{path}` | Upload a file. |
| `GET` | `/v1/files/{path}` | Download a staged file. |
| `DELETE` | `/v1/files/{path}` | Delete a staged file. |

### Management

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/healthz` | Liveness check. Always unauthenticated. |
| `GET` | `/v1/engines` | List configured engines and their capabilities. |
| `GET` | `/api/ps` | List engines currently loaded in memory. |
| `DELETE` | `/api/ps/{engine}` | Evict one engine from memory. |
| `POST` | `/unload` | Evict all loaded engines. |

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `AUDIOLLA_DEVICE` | `auto` | Compute device: `auto`, `cpu`, `cuda`, `cuda:N` |
| `AUDIOLLA_ENGINES_FILE` | `/app/engines.json` | Path to the engines registry JSON |
| `AUDIOLLA_DATA_DIR` | `/data` | Data root — model cache + staged files |
| `AUDIOLLA_AUTH_TOKEN` | _(none)_ | Bearer token for auth. Empty = no auth. |
| `AUDIOLLA_ENABLED_ENGINES` | _(all)_ | Comma-separated slugs to activate. Empty = all. |
| `AUDIOLLA_PRELOAD` | _(none)_ | Comma-separated slugs to load into memory at startup. |
| `AUDIOLLA_ENGINE_TTL` | `600` | Seconds before an idle engine is unloaded. Accepts Go-style durations (`10m`). |
| `AUDIOLLA_SWEEPER_INTERVAL` | `60` | How often the idle-engine sweeper runs, in seconds. |
| `AUDIOLLA_MAX_UPLOAD_BYTES` | `209715200` | Max upload size (default 200 MB). |

---

## What's Not Included

| Feature | Why |
|---------|-----|
| Music generation (text-to-music) | MusicGen is CC-BY-NC — non-commercial only. Stable Audio Open requires a Stability AI commercial agreement. No permissively-licensed model at production quality exists. |
| Essentia MIR analysis | AGPL v3 — using it in a network service requires publishing full source under AGPL. librosa covers the common cases without that obligation. |
| Real-time streaming separation | Demucs needs the whole file. No chunk-based or streaming inference. |
| Speech denoising | resemble-enhance / DeepFilterNet are speech-focused tools. Relevant after Demucs separates vocals, not before. Out of scope. |
| VST3 plugin hosting | Pedalboard supports VST3 but requires mounting the host plugin directory. Not in the default image. |
| Time-stretch / pitch-shift via rubberband | rubberband is GPL v2 + commercial license for distribution. Sox covers basic pitch/tempo shifting. Add rubberband yourself if you accept the terms. |

---

## Build & Development

```bash
make build        # build CPU image
make build-cuda   # build CUDA image
make run          # run CPU image locally (port 8000)
make run-cuda     # run CUDA image locally (port 8000, requires --gpus)
```

```bash
make dev-image          # build the dev container
make shell              # shell inside the dev container
make lint               # flake8 + mypy
make format             # isort + black
make test-unit          # unit tests (no GPU, no ML deps)
make test-unit-cov-gate # enforce ≥80% line coverage on support modules
make test-integration   # integration tests (spawns docker containers)
make generate           # regenerate src/audiolla/schema/ from openapi.yaml
make clean              # remove build/cache artifacts
```

```bash
make pkg-lock                 # refresh uv.lock
make pkg-add PKG=name[==ver]  # add a package
make pkg-update PKG=name      # upgrade one package
make pkg-upgrade              # upgrade everything
make pkg-remove PKG=name      # remove a package
make pkg-compile-heavy        # recompile requirements-heavy-{cpu,cuda}.txt
```

Every `make pkg-*` command bumps `[tool.uv] exclude-newer` in `pyproject.toml` to today's UTC midnight before touching deps, so packages published in the last 24h are refused. Everything runs inside the dev container — the host only needs `docker`, `make`, and `git`.

---

## Supply Chain

Two-layer install in both prod images:

**Light runtime deps** (`fastapi`, `uvicorn`, `pydantic`, etc.) are locked in `uv.lock`. Images install with `uv sync --frozen --no-dev` — build fails if the lockfile is stale, and uv verifies wheel hashes.

**Heavy ML/DSP deps** (torch, demucs, matchering, pedalboard, librosa, sox, numpy, soundfile, huggingface-hub) are split into per-variant hash-locked files because the torch wheel flavor differs between CPU and CUDA images and the wheels live on a separate index (`download.pytorch.org`). The specs live in `scripts/heavy-deps-{cpu,cuda}.in` and compile to `requirements-heavy-{cpu,cuda}.txt` via `make pkg-compile-heavy`. Both files are committed and installed with `uv pip install --require-hashes`.

Base images and the `uv` binary are pinned by `@sha256:` digest.

---

## License

[WTFPL](LICENSE).

matchering and pedalboard are GPL v3 — fine for internal / self-hosted use. Distributing the image as a product requires GPL compliance review.
