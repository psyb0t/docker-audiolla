---
title: "Async jobs and webhooks"
description: "Run long audiolla requests in the background with async_job, poll /v1/jobs, cancel jobs, and receive webhook callbacks."
nav_order: 15
---

# Async jobs and webhooks

Stem separation, generation and long restorations can take minutes. Add `"async_job": true` to the JSON body and the request returns right away with HTTP 202 and a job ID; the work runs in the background. Poll `/v1/jobs/{job_id}` or pass a `webhook_url` and the server POSTs the result to you when it finishes. The queue lives in [`src/audiolla/jobs.py`](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/jobs.py).

## Submit a job

```bash
# stage the input once
curl -X PUT --data-binary @track.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/track.wav

# separate in the background, result staged under stems/
curl -X POST http://localhost:8000/v1/audio/separate \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "engine": "htdemucs",
    "stems": ["vocals"],
    "async_job": true,
    "webhook_url": "https://my-server.example/hooks/audio",
    "output_path": "stems/track-vocals.wav"
  }'
# -> {"job_id":"<uuid>","status":"pending","status_url":"/v1/jobs/<uuid>"}
```

With `async_job: true` the output target is optional. Without `output_path` or `output_url` the result is staged at `jobs/<job_id>.<ext>`, where `<ext>` is the output format (`wav` by default). With `output_url` the result is PUT to that URL when the job finishes, so a presigned S3 PUT URL works:

```bash
curl -X POST http://localhost:8000/v1/audio/master \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "mode": "chain",
    "preset": "transparent",
    "async_job": true,
    "output_url": "https://bucket.s3.amazonaws.com/result.wav?X-Amz-..."
  }'
```

`output_url` needs the fetch policy to allow the host; see [files and remote URLs](files.md). The input is read when you submit, so a bad `file_path` or a refused `file_url` fails the request itself with a 400, not the job.

## Which endpoints queue jobs

50 endpoints run `async_job: true` in the background: every audio-producing endpoint that takes the standard output fields, including `/v1/audio/generate/*`, `/v1/presets/{name}` and `/v1/pipeline`.

These accept `async_job` in their schema but ignore it and run inline: `/v1/midi/render`, `/v1/midi/transform`, `/v1/midi/quantize`, `/v1/midi/humanize` and `/v1/audio/chords-to-midi`. If you send `async_job: true` to them without an output target, the response is the raw MIDI or audio bytes, not a job.

These have no `async_job` field at all and always answer inline: the JSON-only analysis endpoints (`/v1/audio/analyze`, `loudness`, `loudness/curve`, `onsets`, `segments`, `fingerprint`, `chords`, `vad`, `diarize/{engine}`, `tag`, `embed`, `info`, `similar`, `classify`, `clip-detect`, `dj-prep`, `loop-point`, `stereo-field`), `/v1/midi/inspect`, `/v1/midi/compose`, `/v1/midi/drum`, `/v1/midi/generate` and `/v1/batch`. MCP tools have no async option either; see [MCP server](mcp.md).

## Poll, list and cancel

```bash
# one job
curl http://localhost:8000/v1/jobs/<job_id>

# every job, oldest first; filter with ?status=
curl 'http://localhost:8000/v1/jobs?status=running'

# cancel a running job, or remove a finished one
curl -X DELETE http://localhost:8000/v1/jobs/<job_id>
```

A job record has these fields:

| Field | When present | Meaning |
| --- | --- | --- |
| `id` | always | The job ID (a UUID). |
| `endpoint` | always | The endpoint that created it, such as `/v1/audio/separate`. |
| `status` | always | `pending`, `running`, `completed`, `failed` or `cancelled`. |
| `created_at`, `started_at`, `completed_at` | once reached | Unix timestamps in seconds. |
| `result` | completed | The JSON the endpoint would have returned inline, such as `{"path": "...", "size": ...}`. |
| `error` | failed | The error message. |
| `webhook_url` | if given | Where the result is posted. |
| `duration_sec` | completed | Run time, rounded to milliseconds. |

`GET /v1/jobs` returns `{"jobs": [...]}`; an unknown `status` value returns an empty list. An unknown job ID is a 404.

`DELETE /v1/jobs/{job_id}` on a pending or running job cancels its task and answers `{"job_id": "...", "cancelled": true}`; the job then shows `cancelled`. Engine work that already runs in a worker thread can keep going until it returns, but its result is dropped. On a finished job it removes the record and answers `{"job_id": "...", "deleted": true}`. Files the job already wrote stay in the staging area.

## Webhooks

When a job with a `webhook_url` completes, the server POSTs the job record as JSON to that URL:

```json
{
  "id": "<uuid>",
  "endpoint": "/v1/audio/separate",
  "status": "completed",
  "created_at": 1760000000.0,
  "started_at": 1760000000.1,
  "completed_at": 1760000012.5,
  "result": {
    "path": "stems/track-vocals.wav",
    "size": 3145728,
    "output_format": "wav"
  },
  "webhook_url": "https://my-server.example/hooks/audio",
  "duration_sec": 12.4
}
```

- Only completed jobs send a webhook. Failed and cancelled jobs do not; poll for those.
- Delivery makes up to 4 attempts, waiting 0, 1, 2 and 4 seconds before each, with a 10 second timeout per attempt. Any status below 500 counts as delivered, so a 4xx from your endpoint is not retried. 5xx answers and connection errors are retried, and after the fourth failure the server logs a warning and gives up.
- The URL must start with `http://` or `https://`. It is not checked against `AUDIOLLA_FETCH_MODE`, and the request carries no signature, so treat the payload as a hint and confirm with `GET /v1/jobs/{job_id}` if that matters. See [security](security.md).

## Limits and lifetime

- Jobs live in memory only. A container restart loses every job record and webhook still waiting; files already written to the staging area survive.
- There is no concurrency limit. Every submitted job starts at once and competes for CPU, GPU and memory with inline requests. `AUDIOLLA_JOB_MAX_CONCURRENT` is parsed at startup but nothing enforces it yet.
- Finished jobs (completed, failed or cancelled) are removed once they are older than `AUDIOLLA_JOB_TTL` (default `3600` seconds, `1h` also works). The job sweeper checks every 300 seconds, so a record can outlive the TTL by up to five minutes.
- Job retention and file retention are separate. Each running job holds a shared lock on the staging area, and the staged-file sweeper skips its run while any job or `/v1/` request holds one. Once the job ends, its output expires on the normal `AUDIOLLA_FILES_TTL` schedule. Download results you want to keep. See [files](files.md) and [configuration](configuration.md).
