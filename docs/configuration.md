---
title: "Configuration"
description: "Every audiolla environment variable with its default and valid values: device, engines, auth, file retention, URL fetch policy, jobs and logging."
nav_order: 4
---

# Configuration

audiolla reads its settings from environment variables once, at startup, in [src/audiolla/config.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/config.py). A value it cannot parse stops the server with an error naming the variable; it never falls back to the default. Changing a setting means restarting the container.

Pass them with `-e NAME=value` or `--env-file`. [.env.example](https://github.com/psyb0t/docker-audiolla/blob/main/.env.example) lists them all; copy it before you put a token in it, and never commit the copy.

Durations accept plain seconds (`600`, `0.5`) or Go-style strings (`10m`, `1h30m`, `90s`).

## Server and engines

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUDIOLLA_DEVICE` | `auto` in code; `cpu` in the CPU image, `cuda` in the CUDA image | `auto`, `cpu`, `cuda` or `cuda:N`. `auto` picks `cuda` when Torch sees a GPU. Anything else stops startup. |
| `AUDIOLLA_ENGINES_FILE` | `/app/engines.json` | Engine registry to load. See [registry format](engines.md#registry-format). |
| `AUDIOLLA_ENABLED_ENGINES` | empty (all) | Comma-separated slugs to keep from the registry. An unknown slug stops startup, both in `entrypoint.sh` and in the server. |
| `AUDIOLLA_PRELOAD` | empty | Comma-separated slugs to load at startup instead of on first use. Unknown slugs are skipped with a warning. |
| `AUDIOLLA_ENGINE_TTL` | `600` | Duration an engine may sit idle before it is unloaded. `0` keeps engines loaded. |
| `AUDIOLLA_SWEEPER_INTERVAL` | `60` | Duration between idle-engine and staged-file cleanup checks. Must be greater than zero. |
| `AUDIOLLA_LOAD_TIMEOUT` | `300` | Parsed and validated as a duration, but nothing in the current code enforces it. |
| `AUDIOLLA_PRESETS_DIR` | `/app/presets` | Directory of preset YAML files loaded at startup. See [presets](workflows.md). |
| `AUDIOLLA_SOUNDFONT` | empty in code; `/usr/share/sounds/sf2/FluidR3_GM.sf2` in both images | Default SoundFont for MIDI rendering. A request can pass a staged `soundfont_path` instead. |
| `AUDIOLLA_UVR_MODELS_DIR` | `<data dir>/uvr_models` | Where UVR models are cached. |
| `AUDIOLLA_ENABLE_NONCOMMERCIAL` | empty (off) | `1`, `true`, `yes` or `on` lets the MusicGen engines load their CC-BY-NC weights. Without it they refuse. |

## Data and files

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUDIOLLA_DATA_DIR` | `/data` | Root for the staging area (`files/`), `models/` and the UVR cache. |
| `AUDIOLLA_FILES_TTL` | `24h` (86400 seconds) | Staged files older than this, measured from the last write, are deleted. `0` disables deletion. Must be finite and not negative. See [retention](files.md#retention). |
| `AUDIOLLA_MAX_UPLOAD_BYTES` | `209715200` (200 MiB) | Cap on a `PUT /v1/files` body, a staged input, a fetched `file_url` body and a staged output. |

## Authentication

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUDIOLLA_AUTH_TOKEN` | empty (auth off) | When set, every request except `GET /healthz` and `OPTIONS` preflights needs `Authorization: Bearer <token>`, including `/v1/mcp`. See [Security](security.md). |

## Remote URL fetch

These control `file_url` inputs and `output_url` uploads. [Remote URLs](files.md#remote-urls) explains the policy.

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUDIOLLA_FETCH_MODE` | `disabled` | `disabled`, `allowlist` or `denylist`. With `disabled` every `file_url` or `output_url` gets a 400. |
| `AUDIOLLA_FETCH_HOSTS` | empty | Comma-separated hosts: exact names or `*.suffix`. Required and non-empty with `allowlist`; the blocked hosts with `denylist`. `*.example.com` matches `a.example.com` but not `example.com`. |
| `AUDIOLLA_FETCH_SCHEMES` | `https` | Comma-separated, from `http` and `https`. |
| `AUDIOLLA_FETCH_ALLOW_PRIVATE` | `false` | `true` allows hosts that resolve to private, loopback, link-local, multicast, reserved or unspecified addresses. Accepts `1/0`, `true/false`, `yes/no`, `on/off`. |
| `AUDIOLLA_FETCH_TIMEOUT` | `30` | Duration limit per fetch or upload. Connecting has its own 10 second limit. |
| `AUDIOLLA_FETCH_MAX_REDIRECTS` | `5` | Redirects followed per fetch. Each target goes through the same policy. |

## Async jobs

| Variable | Default | Meaning |
| --- | --- | --- |
| `AUDIOLLA_JOB_TTL` | `3600` | Duration a finished job stays queryable before the job sweeper removes it. The sweeper runs every 300 seconds. |
| `AUDIOLLA_JOB_MAX_CONCURRENT` | `8` | Parsed at startup; nothing in the current code enforces it. |

## Logging

| Variable | Default | Meaning |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING` (or `WARN`), `ERROR`, `CRITICAL`, any case. An unknown value prints a warning and uses `INFO`. |

Logs go to stderr, one JSON object per line. Every line has `ts`, `level`, `logger`, `file`, `line`, `func`, `msg`, `service`, `version`, `pid`, `host` and `thread`, plus `request_id`, `method` and `path` while a request is being handled, and `exc` when there is a traceback. The per-request summary line from the `audiolla.request` logger adds `status`, `duration_ms`, `client_ip` (the first `X-Forwarded-For` hop when present), `user_agent`, `req_bytes`, `resp_bytes` and `query`. It logs `/healthz` at `DEBUG`, 2xx and 3xx at `INFO`, 4xx at `WARNING` and 5xx at `ERROR`.

## Hugging Face and Torch

These belong to the libraries, but the images set some of them.

| Variable | Image default | Meaning |
| --- | --- | --- |
| `HF_TOKEN`, `HUGGINGFACE_TOKEN` | empty | Hugging Face access token for gated models. `entrypoint.sh` copies whichever one is set into the other. pyannote reads `HUGGINGFACE_TOKEN` and fails to load without it. |
| `HF_HOME` | `/data/hf` | Hugging Face cache. |
| `HF_HUB_OFFLINE` | `0` | `1` stops Hugging Face downloads; engines whose models are not cached yet then fail to load. |
| `TORCH_HOME` | `<data dir>/torch_cache`, set by `entrypoint.sh` | Torch hub cache, where Demucs checkpoints go. |
| `PYTORCH_CUDA_ALLOC_CONF` | `expandable_segments:True` (CUDA image) | Torch CUDA allocator settings. |
