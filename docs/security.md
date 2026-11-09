---
title: "Security"
description: "What an audiolla server can reach, what it stores and logs, how the bearer token works, and what to set before exposing the port to a network."
nav_order: 20
---

# Security

audiolla is built for a trusted network: your machine, your LAN, a box behind your own reverse proxy. It has one optional shared token, one staging area for everyone and no per-user anything. Read this page before you publish port 8000 beyond loopback.

## Before exposing it

1. Set `AUDIOLLA_AUTH_TOKEN` to a long random value.
2. Put TLS in front of it with a reverse proxy; audiolla serves plain HTTP.
3. Keep `AUDIOLLA_FETCH_MODE=disabled`, or use `allowlist` with the exact storage hosts you need.
4. Restrict `AUDIOLLA_ENABLED_ENGINES` to what you use.
5. Treat the logs as sensitive (see [logs](#logs)).

```bash
docker run -d --name audiolla \
  -e AUDIOLLA_AUTH_TOKEN \
  -v $HOME/.audiolla-data:/data \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest
```

`-e AUDIOLLA_AUTH_TOKEN` with no value passes the variable through from your shell, so the token does not end up in your shell history or in a file.

## Authentication

With `AUDIOLLA_AUTH_TOKEN` set, every HTTP request must carry `Authorization: Bearer <token>`, or it gets a 401 with `{"detail": "..."}` and a `WWW-Authenticate: Bearer` header. The check is ASGI middleware ([src/audiolla/auth.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/auth.py)) in front of everything, including the MCP endpoint at `/v1/mcp`, `/openapi.json` and `/docs`. The token is compared in constant time.

Two things skip the check: `GET /healthz`, so container health checks work, and `OPTIONS` requests, so browser preflights work. Rejected requests are logged with method and path, never the token.

There is one token and it grants everything. There are no roles, no per-user files and no rate limits.

## What a caller can do

Anyone holding the token, or anyone at all when no token is set, can:

- read, overwrite and delete every file in the staging area, including other callers' results;
- run any enabled engine, load models into memory and unload them, and fill the disk up to `AUDIOLLA_MAX_UPLOAD_BYTES` per file;
- start background jobs, list every job and cancel any of them;
- make the server send HTTP requests to URLs they choose, as described below.

Every input is capped at `AUDIOLLA_MAX_UPLOAD_BYTES` (200 MiB by default): staging uploads, staged inputs, downloaded `file_url` bodies, staged outputs and MCP `put_file`. There is no cap on the number of files or on total disk use beyond [retention](files.md#retention).

## Outbound requests

The server makes HTTP requests on a caller's behalf in three places:

- **`file_url` and `output_url` on the REST API and most MCP tools** go through the fetch policy in [src/audiolla/fetch.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/fetch.py): off by default, host allow or deny lists, `https` only by default, private and loopback addresses refused, redirects re-checked, timeouts and a size cap. [Remote URLs](files.md#remote-urls) has the details.
- **Webhooks.** A job's `webhook_url` receives a `POST` when the job completes. This URL is not checked against the fetch policy, so a caller can make the server post to any address it can reach, including private ones. Webhook requests are not signed.
- **Some MCP tools upload to `output_url` without the fetch policy.** `audio_thumbnail`, `chords_to_midi`, `deess`, `drum_pattern` and `midi_humanize` send their result with a plain HTTP `PUT`, skipping the host, scheme and private-address checks, and they do not check the response status.

If untrusted callers can reach the API, the last two let them reach your internal network. Keep such callers out with the token and network rules.

## Paths and files

Every staged path is cleaned and must resolve inside `/data/files`. Traversal (`..`), absolute paths after normalization, backslashes, null bytes and symlinks that escape are refused, and reads and deletes refuse symlinks outright ([files](files.md#path-rules)). Writes go to a `.part` file that is renamed into place.

## Errors

A request that fails validation or hits a handled error gets a 4xx with a `detail` string. An unexpected exception gets a 500 whose `detail` is the exception class and message. Those messages can include file paths inside the container and library internals; do not show them to untrusted users as-is.

## Logs

Logs are JSON lines on stderr. At the default `INFO` level they include:

- every request's method, path, query string, client IP and user agent;
- every fetched and uploaded URL in full, including presigned URL signatures in the query string;
- staged file paths and sizes.

Ship and keep them accordingly.

## The images

- Both images run as uid and gid 1000, not root.
- Base images and the `uv` binary are pinned by digest. Python dependencies are installed from hash-locked files: `uv.lock` for the light dependencies and `requirements-heavy-cpu.txt` or `requirements-heavy-cuda.txt` for the ML stack. New package versions enter only after a seven-day `exclude-newer` window ([pyproject.toml](https://github.com/psyb0t/docker-audiolla/blob/main/pyproject.toml)).
- CI scans both images for known vulnerabilities with Grype and reports findings to the repository's Security tab without failing the build.
- Torch 2.5.1 is affected by [CVE-2025-32434](https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6), which concerns loading untrusted checkpoints. audiolla loads only the model files its engines download from their usual sources. Do not drop checkpoints from elsewhere into `/data/torch_cache`, `/data/uvr_models` or `/data/hf`.
- matchering and pedalboard are GPL v3. Self-hosting is fine; distributing the image as a product needs a GPL compliance review. [THIRD_PARTY.md](https://github.com/psyb0t/docker-audiolla/blob/main/THIRD_PARTY.md) lists the bundled third-party components.

## Reporting a problem

Open an issue at [github.com/psyb0t/docker-audiolla/issues](https://github.com/psyb0t/docker-audiolla/issues). The repository does not take pull requests from outside contributors; they are closed automatically with a request to open an issue instead.
