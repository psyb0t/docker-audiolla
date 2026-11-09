---
title: "REST API reference"
description: "Every audiolla REST endpoint from openapi.yaml: parameters, JSON body fields, defaults, limits and response codes."
nav_order: 17
---

# REST API reference

This page is generated from [`openapi.yaml`](https://github.com/psyb0t/docker-audiolla/blob/main/openapi.yaml), the API contract, so it lists exactly what the spec says: 94 operations, version 2.0.2. The task pages ([getting started](getting-started.md), [files](files.md), [workflows](workflows.md), [jobs](jobs.md)) explain how to use them with examples.

## Basics

- Base URL: `http://localhost:8000` (the container listens on port 8000).
- Authentication: HTTP bearer (`BearerAuth`). When `AUDIOLLA_AUTH_TOKEN` is set, every request needs `Authorization: Bearer <token>`, including `/v1/mcp`. `GET /healthz` is always open. With no token set the API is open. See [security](security.md).
- Input: audio endpoints take a JSON body with exactly one of `file_path` (a path in the [staging area](files.md)) or `file_url` (a URL the server fetches, off unless `AUDIOLLA_FETCH_MODE` allows it). Neither or both is a 400.
- Output: audio-producing endpoints need exactly one of `output_path` (written under the staging area, response `{path, size, ...}`) or `output_url` (a presigned PUT URL, response `{url, size, ...}`). With `async_job: true` both may be omitted and the result goes to `jobs/<job_id>.<ext>`. See [jobs](jobs.md).
- `/v1/midi/compose`, `/v1/midi/generate` and `/v1/midi/drum` are the exception: their body is the spec itself, output options are query parameters, and without `output_path` or `output_url` they return the MIDI or audio bytes directly.
- `PUT /v1/files/{path}` is the only endpoint that takes raw bytes (`application/octet-stream`).
- Errors: a JSON body `{"detail": "..."}` with the status codes listed per operation.
- The running server serves this same spec as JSON at `GET /openapi.json`, and FastAPI's interactive docs at `/docs` and `/redoc`.
- The MCP endpoint at `/v1/mcp` is JSON-RPC and is not in the spec. See [MCP server](mcp.md).

Output formats (`OutputFormat`): `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm`.

## Health

Liveness probes and discovery.

### GET /healthz

Summary: Liveness check (always unauthenticated)

No authentication required.

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Service is up. | `application/json` `HealthResponse` |

## Engines

List, inspect, evict registered engines.

### GET /v1/engines

Summary: List configured engines

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Engine inventory. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |

### GET /v1/catalog

Summary: Machine-readable endpoint catalog

Returns the categorised endpoint list: same data the documentation sidebar uses. Useful for LLM agents discovering what audiolla can do without parsing the full OpenAPI spec.

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Catalog. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |

### GET /v1/ops

Summary: List pipeline op slugs

Ops available to `/v1/pipeline` and `/v1/presets/{name}`.

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Op list. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |

### GET /v1/ps

Summary: List currently loaded engines

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Loaded engines. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |

### DELETE /v1/ps/{engine}

Summary: Evict one engine from memory

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `engine` | path | string | yes |  | Engine slug (e.g. `htdemucs`, `uvr-vocal-bsr`, `basic-pitch`). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Engine evicted. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |

### POST /v1/unload

Summary: Evict every loaded engine

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | All engines evicted. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |

## Files

Local staging area: upload, download, delete files referenced by other endpoints.

### GET /v1/files

Summary: List staged files

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | File listing. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |

### GET /v1/files/{path}

Summary: Download a staged file

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `path` | path | string | yes |  | FILES_DIR-relative path (slashes allowed). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | File bytes. | `application/octet-stream` `AudioBlob` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |

### PUT /v1/files/{path}

Summary: Stage a file (multipart octet-stream upload)

The ONLY endpoint that accepts raw bytes on the wire. All other audio endpoints reference staged files via `file_path` or external URLs via `file_url`.

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `path` | path | string | yes |  | FILES_DIR-relative path (slashes allowed). |

Request body (`AudioBlob`, `application/octet-stream`, required):

Type: `AudioBlob`.

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 201 | File staged. | `application/json` object |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |

### DELETE /v1/files/{path}

Summary: Delete a staged file

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `path` | path | string | yes |  | FILES_DIR-relative path (slashes allowed). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | File deleted. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

## Jobs

Async-job queue: submit, poll, cancel long-running operations.

### GET /v1/jobs

Summary: List async jobs

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Job list. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |

### GET /v1/jobs/{job_id}

Summary: Get job status / result

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | string | yes |  | UUID of an async job. |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Job state. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |

### DELETE /v1/jobs/{job_id}

Summary: Cancel a pending or running job

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `job_id` | path | string | yes |  | UUID of an async job. |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Job cancelled. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |

## Audio Analysis

Audio to JSON. BPM / key / chords / loudness / beats / fingerprint / chroma / VAD / silence / classify / similarity / metadata / info / clip detection.

### POST /v1/audio/analyze

Summary: analyze

Request body (`AudioAnalyzeRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `features` | array of string | no | `[]` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/loudness

Summary: loudness

Request body (`AudioLoudnessRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/beats

Summary: beats

Request body (`AudioBeatsRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `click_track` | boolean | no | `false` |  |  |
| `start_bpm` | number | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/onsets

Summary: onsets

Request body (`AudioOnsetsRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/melody

Summary: melody

Request body (`AudioMelodyRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `fmin` | number | no | `65.0` |  |  |
| `fmax` | number | no | `2093.0` |  |  |
| `as_midi` | boolean | no | `false` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/segments

Summary: segments

Request body (`AudioSegmentsRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `num_segments` | integer | no | `6` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/silence

Summary: silence

Request body (`AudioSilenceRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `threshold_db` | number | no | `-30.0` |  |  |
| `min_duration_sec` | number | no | `0.5` |  |  |
| `trim_mode` | string | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/fingerprint

Summary: fingerprint

Request body (`AudioFingerprintRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `analyze_seconds` | number | no | `120.0` |  |  |
| `return_raw` | boolean | no | `false` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/chords

Summary: chords

Request body (`AudioChordsRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `hop_length` | integer | no | `512` |  |  |
| `segment_min_duration_sec` | number | no | `0.5` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/vad

Summary: vad

Request body (`AudioVadRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `threshold` | number | no | `0.5` |  |  |
| `min_speech_duration_ms` | number | no | `250.0` |  |  |
| `min_silence_duration_ms` | number | no | `100.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/diarize/{engine}

Summary: diarize

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `engine` | path | string | yes |  | Engine slug (e.g. `htdemucs`, `uvr-vocal-bsr`, `basic-pitch`). |

Request body (`AudioDiarizeRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `num_speakers` | integer | no |  | nullable |  |
| `min_speakers` | integer | no |  | nullable |  |
| `max_speakers` | integer | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/tag

Summary: tag

Request body (`AudioTagRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `top_k` | integer | no | `10` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/embed

Summary: embed

Request body (`AudioEmbedRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `query_text` | string | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/info

Summary: audio_info_endpoint

Request body (`AudioInfoRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/similar

Summary: similar

Request body (`AudioSimilarRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `reference_file_path` | string | no |  | nullable | Reference (second) file to compare against. Also accepted as `file_path_b` for the "compare two files" shape that's intuitive when the API is read out of context. |
| `reference_file_url` | string | no |  | nullable | Same as reference_file_path but for an HTTP URL the server fetches (subject to AUDIOLLA_FETCH_MODE policy). Also accepted as `file_url_b`. |
| `file_path_b` | string | no |  | nullable | Alias for reference_file_path. |
| `file_url_b` | string | no |  | nullable | Alias for reference_file_url. |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/classify

Summary: classify

Request body (`AudioClassifyRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `labels` | array of string | yes |  |  | Candidate label strings to score the audio against. |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/metadata

Summary: audio_metadata

Request body (`AudioMetadataRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `tags` | string | no |  | nullable | JSON-encoded tag dict to write. Omit / null = read-only mode (returns the file's current tags). When supplied, the handler writes the tags into the audio file's container and: if `output_path` or `output_url` is also set, persists the tagged audio there. Without an output target, write-mode is no-op-persistent (tags applied to bytes in memory; updated tag set returned in the response; no file landed). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/clip-detect

Summary: clip_detect_endpoint

Request body (`AudioClipDetectRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/beat-slice

Summary: beat_slice_endpoint

Request body (`AudioBeatSliceRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/loudness/curve

Summary: loudness_curve_endpoint

Request body (`AudioLoudnessCurveRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `hop_length` | integer | no | `512` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/loop-point

Summary: loop_point_endpoint

Request body (`AudioLoopPointRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `min_loop_bars` | integer | no | `4` |  |  |
| `num_candidates` | integer | no | `5` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/chords-to-midi

Summary: chords_to_midi

Request body (`AudioChordsToMidiRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `tempo_bpm` | number | no |  | nullable |  |
| `velocity` | integer | no | `80` |  |  |
| `octave` | integer | no | `4` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/stereo-field

Summary: stereo_field_endpoint

Request body (`AudioStereoFieldRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

## Audio Transform

Audio to audio. DSP transforms: normalize, EQ, fade, trim, reverse, speed, stretch, pitch correct, loop, pan, FX, sox chains.

### POST /v1/audio/transform

Summary: transform

Request body (`AudioTransformRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `operations` | array of object | yes |  |  | SoX effect chain: each entry is {op, params}. |
| `operations[].op` | string | no |  |  |  |
| `operations[].params` | object | no |  |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/normalize

Summary: normalize

Request body (`AudioNormalizeRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `target_lufs` | number | yes |  |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `NormalizeResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/fx

Summary: fx

Request body (`AudioFxRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `effects` | array of object | yes |  |  | Pedalboard effect chain: each entry is {type, params}. |
| `effects[].type` | string | no |  |  |  |
| `effects[].params` | object | no |  |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/stretch

Summary: stretch

Request body (`AudioStretchRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `tempo_factor` | number | no | `1.0` |  |  |
| `pitch_semitones` | number | no | `0.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/trim

Summary: trim

Request body (`AudioTrimRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `start_sec` | number | no | `0.0` |  | Trim window start in seconds. Defaults to 0 (beginning of file). |
| `end_sec` | number | no |  | nullable | Trim window end in seconds. Omit (or pass null) to trim to end of source. |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/speed

Summary: speed

Request body (`AudioSpeedRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `speed` | number | yes |  |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/convert

Summary: convert

Request body (`AudioConvertRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `sample_rate` | integer | no |  | nullable |  |
| `channels` | integer | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/fade

Summary: fade

Request body (`AudioFadeRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `fade_in` | number | no | `0.0` |  | Fade-in length in seconds (0 disables). Also accepted as `fade_in_sec`: the `_sec` suffix matches the rest of the API (`start_sec`, `end_sec`, etc.). |
| `fade_in_sec` | number | no |  | nullable | Alias for fade_in. Wins if both are set. |
| `fade_out` | number | no | `0.0` |  | Fade-out length in seconds (0 disables). Also accepted as `fade_out_sec`. |
| `fade_out_sec` | number | no |  | nullable | Alias for fade_out. Wins if both are set. |
| `curve` | string | no | `tri` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/reverse

Summary: reverse

Request body (`AudioReverseRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/loop

Summary: loop

Request body (`AudioLoopRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `count` | integer | no | `2` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/stereo-width

Summary: stereo_width

Request body (`AudioStereoWidthRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `width` | number | no | `1.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/split

Summary: split

Request body (`AudioSplitRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `mode` | string | no | `equal` | one of `equal`, `silence` |  |
| `count` | integer | no |  | nullable |  |
| `threshold_db` | number | no | `-30.0` |  |  |
| `min_duration_sec` | number | no | `0.5` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/pan

Summary: pan

Request body (`AudioPanRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `position` | number | no | `0.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/eq

Summary: eq

Request body (`AudioEqRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `bands` | array of object | yes |  |  | Array of band specifications (object per band). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/mid-side

Summary: mid_side

Request body (`AudioMidSideRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `mode` | string | yes |  | one of `encode`, `decode` |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/pitch-correct

Summary: pitch_correct_endpoint

Request body (`AudioPitchCorrectRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `strength` | number | no | `1.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/thumbnail

Summary: thumbnail_endpoint

Request body (`AudioThumbnailRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `duration_sec` | number | no | `30.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

## Audio Restoration

Audio to audio. Noise reduction, de-essing, multiband compression, dynamics, repair, conv reverb.

### POST /v1/audio/master

Summary: master

Request body (`AudioMasterRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `mode` | string | no |  | one of `reference`, `chain`; nullable | Either `reference` (match against a reference track via matchering) or `chain` (run a pedalboard preset chain). Optional: auto-detected from the request: if reference_path or reference_url is set, mode=reference; else if preset is set, mode=chain; else 400. |
| `reference_path` | string | no |  | nullable |  |
| `reference_url` | string (uri) | no |  | nullable |  |
| `preset` | string | no |  | nullable | For mode=chain, the pedalboard preset to run. Currently 'transparent' or 'loud'. (Note: this is distinct from the workflow presets listed at GET /v1/presets, those are multi-step pipelines invoked via POST /v1/presets/{name}.) |
| `target_lufs` | number | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/restore/{engine}

Summary: restore

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `engine` | path | string | yes |  | Engine slug (e.g. `htdemucs`, `uvr-vocal-bsr`, `basic-pitch`). |

Request body (`AudioRestoreRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `aggressive` | boolean | no | `false` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/enhance/{engine}

Summary: audio_enhance

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `engine` | path | string | yes |  | Engine slug (e.g. `htdemucs`, `uvr-vocal-bsr`, `basic-pitch`). |

Request body (`AudioEnhanceRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/noise-reduce/{engine}

Summary: noise_reduce

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `engine` | path | string | yes |  | Engine slug (e.g. `htdemucs`, `uvr-vocal-bsr`, `basic-pitch`). |

Request body (`AudioNoiseReduceRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `stationary` | boolean | no | `false` |  |  |
| `prop_decrease` | number | no | `1.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/sidechain-duck

Summary: sidechain_duck_endpoint

Request body (`AudioSidechainDuckRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `trigger_file_path` | string | no |  | nullable |  |
| `trigger_file_url` | string | no |  | nullable |  |
| `threshold_db` | number | no | `-20.0` |  |  |
| `ratio` | number | no | `4.0` |  |  |
| `attack_ms` | number | no | `10.0` |  |  |
| `release_ms` | number | no | `200.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/conv-reverb

Summary: conv_reverb_endpoint

Request body (`AudioConvReverbRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `ir_file_path` | string | no |  | nullable |  |
| `ir_file_url` | string | no |  | nullable |  |
| `wet_mix` | number | no | `0.3` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/transient

Summary: transient_endpoint

Request body (`AudioTransientRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `attack_gain_db` | number | no | `0.0` |  |  |
| `sustain_gain_db` | number | no | `0.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/multiband-compress

Summary: multiband_compress_endpoint

Request body (`AudioMultibandCompressRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `crossovers_hz` | array of number | yes |  |  | Ascending crossover frequencies (Hz). 1 fewer than the number of bands. |
| `bands` | array of object | yes |  |  | Array of band specifications (object per band). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/repair

Summary: repair_endpoint

Request body (`AudioRepairRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `declip` | boolean | no | `true` |  |  |
| `dehum` | boolean | no | `false` |  |  |
| `hum_freq` | number | no | `50.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/deess

Summary: deess_endpoint

Request body (`AudioDeessRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `threshold_db` | number | no | `-20.0` |  |  |
| `frequency_hz` | number | no | `6000.0` |  |  |
| `ratio` | number | no | `4.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

## Audio Separation

Stem separation, harmonic/percussive split, vocal isolation, restoration via UVR / Demucs.

### POST /v1/audio/separate

Summary: separate

Request body (`AudioSeparateRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `engine` | string | yes | `htdemucs` |  | Stem-separation engine slug. Demucs (`htdemucs`, `htdemucs_ft`, `mdx_extra`) or UVR variant (`uvr-vocal-bsr`, `uvr-karaoke`, `uvr-dereverb`, etc.). |
| `stems` | array of string | no | `[]` |  | Subset of stems to return. Empty = all available stems. |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/separate/hpss

Summary: hpss

Request body (`AudioSeparateHpssRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `margin` | number | no | `1.0` |  |  |
| `kernel_size` | integer | no | `31` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

## Audio Mixing

Multi-file to audio. Concat, mix, remix, BPM/key match, DJ prep, batch.

### POST /v1/audio/mix

Summary: mix

Request body (`AudioMixRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_paths` | array of string | no |  | min items 1; nullable |  |
| `file_urls` | array of string (uri) | no |  | min items 1; nullable |  |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/concat

Summary: concat

Request body (`AudioConcatRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_paths` | array of string | no |  | min items 1; nullable |  |
| `file_urls` | array of string (uri) | no |  | min items 1; nullable |  |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/bpm-match

Summary: bpm_match

Request body (`AudioBpmMatchRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `target_bpm` | number | yes |  |  |  |
| `pitch_semitones` | number | no | `0.0` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/key-match

Summary: key_match

Request body (`AudioKeyMatchRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `target_key` | string | yes |  |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/remix

Summary: remix

Request body (`AudioRemixRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `engine` | string | no | `htdemucs` |  | Stem-separation engine for the unmix step. |
| `stem_mix` | object | no |  |  | Per-stem gain dict: keys are stem names ('vocals', 'drums', 'bass', 'other'), values are linear gain multipliers (1.0 = keep, 0.0 = mute, 0.5 = -6 dB). Missing stems default to 1.0. |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/dj-prep

Summary: dj_prep

Request body (`AudioDjPrepRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/batch

Summary: Apply a single operation to many input files at once

Run the same transform against a list of staged files (or URLs). Body is a JSON array of independent per-file request objects (the same shape the underlying operation takes). Server returns a JSON list of per-file results.

Request body (`application/json`, required):

Type: array of object.

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Per-file result array. | `application/json` array of object |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

## Audio Generation

Text to audio. Stable Audio Open, MusicGen, Riffusion, AudioLDM 2.

### POST /v1/audio/generate/stable-audio-open

Summary: Stability Stable Audio Open 1.0: text-to-audio.

Request body (`StableAudioOpenRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `prompt` | string | yes |  | min length 1 |  |
| `duration_sec` | number | no | `10.0` | min 0.001 |  |
| `seed` | integer | no |  | nullable |  |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `num_inference_steps` | integer | no | `100` | min 1; max 500 |  |
| `negative_prompt` | string | no | `low quality, average quality` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio generated. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |

### POST /v1/audio/generate/musicgen-small

Summary: Meta MusicGen 300M: CC-BY-NC, opt-in required.

Request body (`MusicGenRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `prompt` | string | yes |  | min length 1 |  |
| `duration_sec` | number | no | `10.0` | min 0.001 |  |
| `seed` | integer | no |  | nullable |  |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `lyrics` | string | no |  | nullable | Accepted for API uniformity; MusicGen is instrumental-only. |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio generated. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |

### POST /v1/audio/generate/musicgen-medium

Summary: Meta MusicGen 1.5B: CC-BY-NC.

Request body (`MusicGenRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `prompt` | string | yes |  | min length 1 |  |
| `duration_sec` | number | no | `10.0` | min 0.001 |  |
| `seed` | integer | no |  | nullable |  |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `lyrics` | string | no |  | nullable | Accepted for API uniformity; MusicGen is instrumental-only. |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio generated. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |

### POST /v1/audio/generate/riffusion

Summary: Riffusion v1: spectrogram via Griffin-Lim.

Request body (`RiffusionRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `prompt` | string | yes |  | min length 1 |  |
| `duration_sec` | number | no | `10.0` | min 0.001 |  |
| `seed` | integer | no |  | nullable |  |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio generated. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |

### POST /v1/audio/generate/audioldm2

Summary: AudioLDM 2: CC-BY 4.0, general SFX.

Request body (`AudioLDM2Request`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `prompt` | string | yes |  | min length 1 |  |
| `duration_sec` | number | no | `10.0` | min 0.001 |  |
| `seed` | integer | no |  | nullable |  |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `num_inference_steps` | integer | no | `200` | min 1; max 500 |  |
| `negative_prompt` | string | no | `Low quality.` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio generated. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |

## Audio Visualization

Audio to image/video. Spectrogram, waveform, animated visualizers.

### POST /v1/audio/visualize/image/spectrogram

Summary: visualize_spectrogram

Request body (`AudioVisualizeImageSpectrogramRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `width` | integer | no | `1280` |  |  |
| `height` | integer | no | `720` |  |  |
| `color` | string | no | `intensity` |  |  |
| `scale` | string | no | `log` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/visualize/image/waveform

Summary: visualize_waveform

Request body (`AudioVisualizeImageWaveformRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `width` | integer | no | `1280` |  |  |
| `height` | integer | no | `720` |  |  |
| `color` | string | no | `lime` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/visualize/video/{mode}

Summary: visualize_video

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `mode` | path | string | yes |  | Endpoint-specific mode token (e.g. `encode`/`decode` for mid-side). |

Request body (`AudioVisualizeVideoRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `width` | integer | no | `1280` |  |  |
| `height` | integer | no | `720` |  |  |
| `fps` | integer | no | `30` |  |  |
| `container` | string | no | `mp4` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

## MIDI

MIDI composition, rendering, transformation, audio to MIDI transcription.

### POST /v1/midi/render

Summary: midi_render

Request body (`MidiRenderRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `soundfont_path` | string | no |  | nullable |  |
| `gain` | number | no | `0.5` |  |  |
| `samplerate` | integer | no | `44100` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/midi/inspect

Summary: midi_inspect

Request body (`MidiInspectRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | JSON result. | `application/json` object |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/midi/transform

Summary: midi_transform

Request body (`MidiTransformRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `transpose_semitones` | integer | no | `0` |  |  |
| `quantize_grid_beats` | number | no |  | nullable |  |
| `tempo_bpm` | number | no |  | nullable |  |
| `keep_channels` | string | no |  | nullable |  |
| `drop_channels` | string | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/audio/to_midi/{engine}

Summary: to_midi

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `engine` | path | string | yes |  | Engine slug (e.g. `htdemucs`, `uvr-vocal-bsr`, `basic-pitch`). |

Request body (`AudioToMidiRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `onset_threshold` | number | no | `0.5` |  |  |
| `frame_threshold` | number | no | `0.3` |  |  |
| `minimum_note_length_ms` | number | no | `58.0` |  |  |
| `minimum_frequency` | number | no |  | nullable |  |
| `maximum_frequency` | number | no |  | nullable |  |
| `multiple_pitch_bends` | boolean | no | `false` |  |  |
| `melodia_trick` | boolean | no | `true` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/midi/quantize

Summary: midi_quantize

Request body (`MidiQuantizeRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `grid_beats` | number | no | `0.25` |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/midi/humanize

Summary: midi_humanize

Request body (`MidiHumanizeRequest`, `application/json`, required):

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable | FILES_DIR-relative path (pre-staged via PUT /v1/files/{path}). |
| `file_url` | string (uri) | no |  | nullable | HTTP/HTTPS URL the server fetches (subject to AUDIOLLA_FETCH_MODE). |
| `output_format` | `OutputFormat` | no | `wav` | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `output_path` | string | no |  | nullable | FILES_DIR-relative path; response is JSON {path, size, ...}. |
| `output_url` | string (uri) | no |  | nullable | Presigned PUT URL (S3, hybrids3, MinIO, R2, etc.): response is JSON {url, size, ...}. |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `timing_ms` | number | no | `10.0` |  |  |
| `velocity_pct` | number | no | `10.0` |  |  |
| `seed` | integer | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio produced. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/midi/compose

Summary: Compose a song spec to a Standard MIDI File

Body is the song spec (tempo_bpm, time_signature, key_signature, ticks_per_beat, tracks). Server returns raw MIDI bytes by default, or JSON descriptor when `output_path` / `output_url` are set as query parameters.

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `output_path` | query | string | no |  |  |
| `output_url` | query | string (uri) | no |  |  |

Request body (`application/json`, required):

A free-form JSON object (see the description above).

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | MIDI bytes or staged-output JSON. | `audio/midi` `AudioBlob`; `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/midi/drum

Summary: Generate a drum-pattern MIDI clip

JSON spec body to MIDI bytes or staged-output JSON.

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `output_path` | query | string | no |  |  |
| `output_url` | query | string (uri) | no |  |  |

Request body (`application/json`, required):

A free-form JSON object (see the description above).

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | MIDI bytes or staged-output JSON. | `audio/midi` `AudioBlob`; `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### POST /v1/midi/generate

Summary: Compose + render in one call

Convenience wrapper: takes the same song spec body as `/v1/midi/compose`, immediately runs `/v1/midi/render`. Returns rendered audio bytes or a staged-output JSON descriptor.

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `output_format` | query | `OutputFormat` | no |  |  |
| `soundfont_path` | query | string | no |  |  |
| `gain` | query | number | no | `0.5` |  |
| `samplerate` | query | integer | no | `44100` |  |
| `output_path` | query | string | no |  |  |
| `output_url` | query | string (uri) | no |  |  |

Request body (`application/json`, required):

A free-form JSON object (see the description above).

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Audio bytes or staged-output JSON. | `audio/wav` `AudioBlob`; `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

## Workflow

Presets, ad-hoc pipelines, named workflows.

### POST /v1/pipeline

Summary: Ad-hoc op chain across one input

Apply N transforms in order to one input. Body is `{file_path | file_url, steps: [{op, params}, ...], output_path | output_url}`. Intermediates stay in memory between steps: no re-upload required.

Request body (`PipelineRunRequest`, `application/json`, required):

Body for `POST /v1/pipeline`. Apply N transforms in order to one input. Intermediates stay in memory between steps: no re-upload required.

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable |  |
| `file_url` | string (uri) | no |  | nullable |  |
| `steps` | array of object | yes |  |  |  |
| `steps[].op` | string | yes |  |  |  |
| `steps[].params` | object | no |  |  |  |
| `output_path` | string | no |  | nullable |  |
| `output_url` | string (uri) | no |  | nullable |  |
| `output_format` | `OutputFormat` | no |  | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Pipeline executed. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |

### GET /v1/presets

Summary: List configured workflow presets

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Preset list. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |

### GET /v1/presets/{name}

Summary: Describe a single preset

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `name` | path | string | yes |  |  |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Preset description. | `application/json` object |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |

### POST /v1/presets/{name}

Summary: Run a named preset

Parameters:

| Name | In | Type | Required | Default | Description |
| --- | --- | --- | --- | --- | --- |
| `name` | path | string | yes |  |  |

Request body (`PresetRunRequest`, `application/json`, required):

Body for `POST /v1/presets/{name}`. The preset's steps are baked into the server-side preset definition; the request only specifies the input + output destination and optional per-step param overrides.

| Field | Type | Required | Default | Constraints | Description |
| --- | --- | --- | --- | --- | --- |
| `file_path` | string | no |  | nullable |  |
| `file_url` | string (uri) | no |  | nullable |  |
| `output_path` | string | no |  | nullable |  |
| `output_url` | string (uri) | no |  | nullable |  |
| `output_format` | `OutputFormat` | no |  | one of `wav`, `mp3`, `flac`, `opus`, `aac`, `pcm` |  |
| `async_job` | boolean | no | `false` |  |  |
| `webhook_url` | string (uri) | no |  | nullable |  |
| `params` | object | no |  | nullable | Override values for parameters the preset declares. |

Responses:

| Status | Description | Body |
| --- | --- | --- |
| 200 | Preset executed. | `application/json` `StagedOutputResponse` or `UrlOutputResponse` |
| 202 | Async job accepted. | `application/json` `JobAcceptedResponse` |
| 400 | Bad request: invalid input or constraint violation. | `application/json` `ErrorBody` |
| 401 | Missing or invalid bearer token. | `application/json` `ErrorBody` |
| 404 | Engine or file not found. | `application/json` `ErrorBody` |
| 413 | Payload too large. | `application/json` `ErrorBody` |
| 415 | Unsupported output format / media type. | `application/json` `ErrorBody` |
| 422 | Validation error: request body schema mismatch. | `application/json` `ErrorBody` |
| 500 | Internal server error. | `application/json` `ErrorBody` |
