---
title: "Troubleshooting"
description: "audiolla startup refusals and request errors with the exact message, the cause and the fix: config values, engines, staging paths, URLs, tokens."
nav_order: 21
---

# Troubleshooting

Messages below are copied from the source so you can search for them. Request errors come back as `{"detail": "<message>"}`; startup errors appear in the container log (`docker logs audiolla`).

## The container exits at startup

audiolla checks its configuration before it serves anything and exits on a bad value ([configuration](configuration.md)).

| Message | Cause and fix |
| --- | --- |
| `[entrypoint] AUDIOLLA_ENABLED_ENGINES contains unknown slug(s) [...]; known: [...]` | A slug in `AUDIOLLA_ENABLED_ENGINES` is not in this image's registry. The CPU image has no `htdemucs_ft`, `htdemucs_6s`, `mdx_extra` or generators. Remove the slug or use the CUDA image. |
| `AUDIOLLA_DEVICE='...' must be 'auto', 'cpu', 'cuda', or 'cuda:N'` | Typo in `AUDIOLLA_DEVICE`. |
| `AUDIOLLA_FETCH_MODE=allowlist requires AUDIOLLA_FETCH_HOSTS to be a non-empty comma-separated list` | Allowlist mode with no hosts. Set `AUDIOLLA_FETCH_HOSTS`. |
| `AUDIOLLA_FETCH_MODE='...' must be 'disabled', 'allowlist', or 'denylist'` | Unknown fetch mode. |
| `AUDIOLLA_FETCH_SCHEMES contains unsupported scheme '...'; supported: http, https` | Only `http` and `https` are allowed. |
| `AUDIOLLA_FETCH_ALLOW_PRIVATE='...' must be a boolean (1/0, true/false, yes/no, on/off)` | Use one of those values. |
| `AUDIOLLA_FILES_TTL must be finite and nonnegative; 0 disables cleanup` | Negative or infinite TTL. |
| `AUDIOLLA_SWEEPER_INTERVAL must be finite and greater than zero` | `0` or a negative interval. |
| `<NAME>='...' must be seconds (e.g. 600) or Go-style duration like '3h30m5s', '45m', '90s'` | A duration variable has an unparsable value. |
| `<NAME>='...' is not an integer` | `AUDIOLLA_MAX_UPLOAD_BYTES`, `AUDIOLLA_FETCH_MAX_REDIRECTS` or `AUDIOLLA_JOB_MAX_CONCURRENT` is not a whole number. |
| `engines.json not found at <path>` | `AUDIOLLA_ENGINES_FILE` points at a missing file. |
| `<path>: engine '<slug>' executor='<x>' must be one of [...]` | A custom registry uses an executor audiolla does not have. See [registry format](engines.md#registry-format). |
| `AUDIOLLA_ENABLED_ENGINES references unknown slug(s) [...]` | Same as the entrypoint message, raised by the server when `entrypoint.sh` was bypassed. |

A Demucs download failure does not stop startup. It logs `[entrypoint] WARN: demucs <variant> prefetch failed: ...` and the first separation with that engine tries again.

## Requests fail

| Status and message | Cause and fix |
| --- | --- |
| 401 `missing Authorization: Bearer header` or `invalid bearer token` | Auth is on. Send `-H "Authorization: Bearer $AUDIOLLA_AUTH_TOKEN"`. |
| 400 `must provide exactly one of: file_path, file_url` | The body has no input, or the field name is wrong. |
| 400 `file_path and file_url are mutually exclusive` | Send one of the two. |
| 400 `audio-producing endpoint requires output_path or output_url (sync mode); use async_job=true for auto-staged jobs/{id}.{ext}` | Add `"output_path": "out/result.wav"`, or run it as an [async job](jobs.md). |
| 400 `output_path and output_url are mutually exclusive` | Send one of the two. |
| 404 `staged file not found: <path>` | Nothing is staged at that path, or it expired. List with `GET /v1/files`; see [retention](files.md#retention). |
| 400 `path contains forbidden segment '..'` and other `path ...` messages | The staged path breaks the [path rules](files.md#path-rules). |
| 400 `staged file is empty: <path>` | The staged file has zero bytes. Upload it again with `--data-binary @file`. |
| 413 `upload too large (...)`, `staged file too large (...)`, `output too large to stage (...)` | Over `AUDIOLLA_MAX_UPLOAD_BYTES`. Raise it or split the audio. |
| 400 `URL fetch/upload is disabled (AUDIOLLA_FETCH_MODE=disabled); use file/file_path instead` | `file_url` or `output_url` with the default policy. Stage the file, or [enable remote URLs](files.md#remote-urls). |
| 400 `host '...' not in AUDIOLLA_FETCH_HOSTS allowlist` | Add the host or a `*.` pattern. |
| 400 `host '...' resolves to private/loopback IP ...; set AUDIOLLA_FETCH_ALLOW_PRIVATE=true to allow` | The URL points at a private address, such as MinIO on your LAN. Allow private addresses only if you trust every caller. |
| 415 `unsupported output_format '...'; supported: [...]` | Use `wav`, `mp3`, `flac`, `opus`, `aac` or `pcm`. |
| 404 `unknown engine '<slug>'; configured: [...]` | The engine is not in this image or not enabled. |
| 404 `<slug> engine not configured` | The endpoint needs an engine that `AUDIOLLA_ENABLED_ENGINES` left out. See [which endpoints need which engine](engines.md#which-endpoints-need-which-engine). |
| 400 `engine '<slug>' is cuda_only ...` | `htdemucs_ft` on a CUDA image running without a GPU. Start it with `--gpus all`. |
| 400 `HUGGINGFACE_TOKEN env var is required for pyannote diarization` | Set `HF_TOKEN` or `HUGGINGFACE_TOKEN` and accept the model terms on huggingface.co. |
| 400 `<slug>: weights are CC-BY-NC-licensed. Set AUDIOLLA_ENABLE_NONCOMMERCIAL=1 ...` | MusicGen needs the opt-in. Read the license first. |
| 400 `target_lufs must be in [-70.0, -0.1], got ...` | Loudness target out of range. |
| 422 with a list of field errors | The body does not match the schema, for example a string where a number belongs. Check the field in the [API reference](api.md). |
| 500 `<ExceptionClass>: <message>` | An unexpected error. The traceback is in the log under the same `request_id` as the response's `X-Request-Id` header. |

## Slow or stuck

- **The first call to an engine takes long.** It is loading or downloading weights. Preload with `AUDIOLLA_PRELOAD`, and keep `/data` mounted so downloads happen once.
- **A call that used to be fast is slow again.** Heavy endpoints unload every other engine before they run, and idle engines unload after `AUDIOLLA_ENGINE_TTL`. Alternating between two heavy engines reloads each time. See [loading and unloading](engines.md#loading-and-unloading).
- **Staged files never expire.** The sweep skips its turn while any `/v1/` request or job is running, on any container sharing `/data`. A server under constant load never sweeps. See [retention](files.md#retention).
- **A long request times out at your proxy.** Run it with `"async_job": true` and poll `/v1/jobs/{job_id}`.

## Getting more detail

Set `LOG_LEVEL=DEBUG` and repeat the request. Every log line during a request carries the same `request_id`, which is also returned in the `X-Request-Id` response header; send your own `X-Request-Id` to choose it.
