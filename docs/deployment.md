---
title: "Deployment"
description: "Run the audiolla CPU or CUDA image: tags, the /data volume layout, GPU flags, restricting engines, Hugging Face tokens and upgrade notes."
nav_order: 3
---

# Deployment

audiolla ships as two Docker images built from the same source. This page covers picking one, running it, what it writes to disk and what changes between versions.

## Images and tags

| Image | Built from | Device | Engine registry |
| --- | --- | --- | --- |
| `psyb0t/audiolla:latest` | [Dockerfile](https://github.com/psyb0t/docker-audiolla/blob/main/Dockerfile) | CPU | [engines-cpu.json](https://github.com/psyb0t/docker-audiolla/blob/main/engines-cpu.json), 27 engines |
| `psyb0t/audiolla:latest-cuda` | [Dockerfile.cuda](https://github.com/psyb0t/docker-audiolla/blob/main/Dockerfile.cuda) | NVIDIA GPU | [engines.json](https://github.com/psyb0t/docker-audiolla/blob/main/engines.json), 35 engines |

Every release is also tagged `vX.Y.Z` and `vX.Y.Z-cuda`, and every build of `main` is tagged `sha-<commit>` and `sha-<commit>-cuda`. Both images are `linux/amd64` only.

The CPU image lacks `htdemucs_ft`, `htdemucs_6s`, `mdx_extra` and the five music and SFX generators; asking it for one gets a 404 for an unknown engine. The [engines](engines.md) page lists what each image has.

Both images start from [Torchbase](https://github.com/psyb0t/torchbase) (Python 3.12, Torch 2.5.1, CPU or CUDA 12.4 wheels), run as the non-root user `1000:1000`, listen on port 8000 and carry a Docker `HEALTHCHECK` that polls `/healthz` every 30 seconds.

## Run

```bash
# CPU
docker run -d --name audiolla \
  -v $HOME/.audiolla-data:/data \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest

# NVIDIA GPU (needs the NVIDIA Container Toolkit on the host)
docker run -d --name audiolla \
  --gpus all \
  -v $HOME/.audiolla-data:/data \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest-cuda
```

The examples publish the port on loopback only. Read [Security](security.md) before you publish it anywhere else, and set `AUDIOLLA_AUTH_TOKEN` if you do.

The CPU image sets `AUDIOLLA_DEVICE=cpu` and the CUDA image sets `AUDIOLLA_DEVICE=cuda`. Pass `-e AUDIOLLA_DEVICE=cuda:1` to pick a GPU. All settings are environment variables; [Configuration](configuration.md) lists them, and [.env.example](https://github.com/psyb0t/docker-audiolla/blob/main/.env.example) is a starting point for `docker run --env-file`.

The server port is fixed at 8000 inside the container (`src/audiolla/__main__.py` starts uvicorn on `0.0.0.0:8000`). Change the host side of `-p` to move it.

## What lives in /data

Mount `/data` on a volume the container's user (uid 1000) can write. Everything audiolla keeps between restarts is under it:

| Path | What | Written by |
| --- | --- | --- |
| `/data/files/` | The staging area behind `/v1/files`, including async job results under `jobs/` | API calls |
| `/data/torch_cache/` | Demucs checkpoints (`TORCH_HOME`) | `entrypoint.sh` at startup |
| `/data/uvr_models/` | UVR restoration and separation models (`AUDIOLLA_UVR_MODELS_DIR`) | the first call to a `uvr-*` engine |
| `/data/hf/` | Hugging Face model cache (`HF_HOME`): AST, CLAP, pyannote, the generators | the first call to those engines |
| `/data/models/` | Created at startup, reserved for per-engine snapshots | `entrypoint.sh` |
| `/data/.files-cleanup.lock` | Lock file that coordinates file retention between containers | the server |

Staged files expire after `AUDIOLLA_FILES_TTL` (24 hours by default); the model caches never expire. Deleting a cache directory forces a fresh download on next use. Back up `/data/files/` only if you keep results there; everything else can be downloaded again.

A CPU and a CUDA container can share one `/data`. The retention sweep takes an exclusive lock on `/data/.files-cleanup.lock` and skips its turn while either container is serving a `/v1/` request or running a job ([files](files.md#retention)).

## First start and model downloads

`entrypoint.sh` runs before the server:

1. It mirrors `HF_TOKEN` and `HUGGINGFACE_TOKEN` into each other, so setting either one works.
2. It creates `/data/models`, `/data/files` and `/data/torch_cache/hub/checkpoints`.
3. It checks `AUDIOLLA_ENABLED_ENGINES` against the registry and exits with an error listing the known slugs if one is unknown.
4. It downloads the checkpoint of every enabled Demucs engine (`htdemucs` on the CPU image; `htdemucs`, `htdemucs_ft`, `htdemucs_6s` and `mdx_extra` on the CUDA image). A failed download is logged as a warning and the server starts anyway.
5. It starts the server with `python3 -m audiolla`.

Every other engine loads its weights on the first request that needs it, so that request is slow. Load engines at startup instead with `AUDIOLLA_PRELOAD=deepfilter,silero-vad`.

To start faster and use less memory and disk, enable only the engines you need:

```bash
docker run -d --name audiolla \
  -e AUDIOLLA_ENABLED_ENGINES=htdemucs,librosa-analyze,chord-detect,basic-pitch,midi-compose,midi-render \
  -v $HOME/.audiolla-data:/data \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest
```

An endpoint whose engine is not enabled answers 404: `unknown engine '<slug>'` when you named the engine in the path or body, or `<slug> engine not configured` when the endpoint needs a fixed engine, such as `librosa-analyze` and `stretch` for `/v1/audio/bpm-match`. The [engines](engines.md#which-endpoints-need-which-engine) page maps endpoints to engines.

## Gated models and Hugging Face tokens

Some engines download weights you must accept a license for on huggingface.co first. pyannote speaker diarization needs a token at load time and fails without one; Stable Audio Open is a gated repository. Set the token as an environment variable, never in a file you commit:

```bash
docker run -d --name audiolla \
  --gpus all \
  -e HF_TOKEN \
  -v $HOME/.audiolla-data:/data \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest-cuda
```

`-e HF_TOKEN` with no value passes the variable through from your shell. The MusicGen engines also need `AUDIOLLA_ENABLE_NONCOMMERCIAL=1` because their weights are CC-BY-NC; see [generation](generation.md).

## Health and logs

`GET /healthz` is never behind auth and answers `{"ok": true, "device": "...", "engines": [...]}`. `GET /v1/engines` shows each engine's `loaded` state and `idle_seconds`; `GET /v1/ps` lists only the loaded ones.

Logs go to stderr as one JSON object per line, at the level set by `LOG_LEVEL`. Each HTTP request gets one summary line from the `audiolla.request` logger with `request_id`, `method`, `path`, `status` and `duration_ms`. Send an `X-Request-Id` header and the server uses it and echoes it back; otherwise it generates one. [Configuration](configuration.md#logging) has the field list.

## Upgrading

Pull the new tag and recreate the container with the same `/data` mount. Read the [CHANGELOG](https://github.com/psyb0t/docker-audiolla/blob/main/CHANGELOG.md) first: a major version bump breaks something.

### v2.0.0: staged files expire

From v2.0.0, staged files are deleted 24 hours after their last write. If an installation must keep files indefinitely, set `AUDIOLLA_FILES_TTL=0` before you start the new image. REST and MCP request shapes did not change.

### v1.0.0: JSON bodies and staged inputs

v1.0.0 broke every v0.23.x client:

- Every audio endpoint takes a JSON body. Multipart uploads are gone, and the staging area takes raw bytes with `PUT /v1/files/{path}`.
- Input is `file_path` or `file_url`; output is `output_path` or `output_url`. Responses no longer carry audio bytes.
- `async_job=true` stages the result to `jobs/<id>.<ext>` when no output is given.
- MCP tools that produced audio dropped `audio_base64`, `midi_base64`, `image_base64` and `video_base64` and take the same output fields.

```diff
- curl -X POST http://localhost:8000/v1/audio/normalize \
-     -F "file=@track.wav" -F "target_lufs=-14" -o normalized.wav

+ # 1) stage the file
+ curl -X PUT --data-binary @track.wav \
+     -H 'Content-Type: application/octet-stream' \
+     http://localhost:8000/v1/files/uploads/track.wav

+ # 2) process with a JSON body; the response is JSON, not bytes
+ curl -X POST http://localhost:8000/v1/audio/normalize \
+     -H 'Content-Type: application/json' \
+     -d '{"file_path":"uploads/track.wav","target_lufs":-14,"output_path":"out/normalized.wav"}'

+ # 3) download the result
+ curl -o normalized.wav http://localhost:8000/v1/files/out/normalized.wav
```

The v1.0.0 entry in the [CHANGELOG](https://github.com/psyb0t/docker-audiolla/blob/main/CHANGELOG.md) has the full list and the reasons.

## Building the images yourself

```bash
make build        # CPU image: psyb0t/audiolla:local, :v<version>, :latest
make build-cuda   # CUDA image: psyb0t/audiolla:local-cuda, :v<version>-cuda, :latest-cuda
make run          # build and run the CPU image on port 8000 with ~/.audiolla-data
make run-cuda     # same with --gpus all
```

[Development](development.md) covers the rest of the Makefile.
