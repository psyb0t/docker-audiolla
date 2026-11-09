---
title: "Files and remote URLs"
description: "Stage, list, download and delete files under /v1/files, how staged files expire, and how to let audiolla fetch from and upload to remote URLs."
nav_order: 5
---

# Files and remote URLs

Audio endpoints read their input from the server's staging area or from a URL, and write their output to one of the same two places. This page covers both.

## The staging area

`/v1/files` is a plain file store under `/data/files` inside the container. Upload a file once, then use its path as `file_path` on any number of requests, and download results written with `output_path`.

```bash
# upload: the request body is the raw file
curl -X PUT --data-binary @track.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/track.wav
# -> {"path":"uploads/track.wav","size":5292044}

# list every staged file
curl http://localhost:8000/v1/files
# -> {"files":[{"path":"uploads/track.wav","size":5292044,"modified":"2026-11-09T12:00:00Z"}]}

# download
curl -o copy.wav http://localhost:8000/v1/files/uploads/track.wav

# delete
curl -X DELETE http://localhost:8000/v1/files/uploads/track.wav
# -> {"deleted":"uploads/track.wav"}
```

`PUT` returns 201 and replaces an existing file. It writes to a `.part` file first and renames it, so a reader never sees half a file. A body larger than `AUDIOLLA_MAX_UPLOAD_BYTES` (200 MiB by default) gets a 413. Deleting a file also removes directories it leaves empty.

Once staged, refer to the file by path:

```bash
curl -X POST http://localhost:8000/v1/audio/analyze \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","features":["bpm"]}'
```

MCP clients get the same store through the `list_files`, `put_file` (content as base64), `get_file` and `delete_file` tools. `get_file` returns only the path and size; download the bytes with `GET /v1/files/{path}`. See [MCP server](mcp.md).

### Path rules

The server cleans every path before touching the disk ([src/audiolla/files.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/files.py)):

- Leading slashes and an optional `files/` or `v1/files/` prefix are stripped, so `uploads/a.wav`, `/uploads/a.wav` and `/v1/files/uploads/a.wav` name the same file.
- Empty paths, null bytes, backslashes, empty segments (`a//b`) and `.` or `..` segments get a 400.
- The resolved path has to stay inside `/data/files`; anything that escapes, for example through a symlink, gets a 400.
- Reads, downloads and deletes refuse symlinks with a 404, and listings skip them.

The same rules apply to `file_path`, `output_path`, `soundfont_path` and every other staged path a request takes.

There is one staging area for the whole server. Anyone who can call the API can read, overwrite and delete every staged file; see [Security](security.md).

## Retention

Staged files are deleted once they are older than `AUDIOLLA_FILES_TTL`, 24 hours by default. Age counts from the last write (the file's modification time), not the last read. Set a duration such as `48h` or `172800`, or `0` to keep files forever. Download anything you want to keep before it expires.

A sweep runs every `AUDIOLLA_SWEEPER_INTERVAL` seconds (default 60). It deletes regular files only: `.part` files and symlinks are left alone, and nothing outside `/data/files` (such as the model caches) is touched. Empty directories stay.

The sweep never runs while the server is busy. Every `/v1/` request and every running async job holds a shared lock on `/data/.files-cleanup.lock`, and the sweep needs the exclusive lock, so it skips its turn and tries again next interval. Containers that share `/data`, such as a CPU and a CUDA container, use the same lock file and do not delete each other's files mid-request. A server that is never idle never sweeps. Open MCP event streams (`GET /v1/mcp`) do not hold the lock.

Job records have their own lifetime, `AUDIOLLA_JOB_TTL`; see [Async jobs](jobs.md).

## Remote URLs

`file_url` makes the server download its input, and `output_url` makes it upload the result with an HTTP `PUT`. Both are off by default: with `AUDIOLLA_FETCH_MODE=disabled` any request carrying one gets a 400. Turn them on at container start:

```bash
docker run -d --name audiolla \
  -e AUDIOLLA_FETCH_MODE=allowlist \
  -e AUDIOLLA_FETCH_HOSTS="*.s3.amazonaws.com,*.r2.cloudflarestorage.com" \
  -v $HOME/.audiolla-data:/data \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest
```

Then fetch from one presigned URL and upload to another:

```bash
curl -X POST http://localhost:8000/v1/audio/master \
  -H 'Content-Type: application/json' \
  -d '{
    "file_url": "https://my-bucket.s3.amazonaws.com/in.wav?X-Amz-Signature=...",
    "reference_url": "https://my-bucket.s3.amazonaws.com/ref.wav?X-Amz-Signature=...",
    "mode": "reference",
    "output_url": "https://my-bucket.s3.amazonaws.com/out.wav?X-Amz-Signature=..."
  }'
# -> {"url":"https://my-bucket.s3.amazonaws.com/out.wav?...","size":...,...}
```

The upload sends the file with a `Content-Type` matching the output format and counts 200, 201 and 204 as success. Any other answer, or any policy refusal, is a 400 with the reason in `detail`.

### Fetch policy

| `AUDIOLLA_FETCH_MODE` | Effect |
| --- | --- |
| `disabled` (default) | `file_url` and `output_url` are rejected. |
| `allowlist` | Only hosts matching `AUDIOLLA_FETCH_HOSTS` are allowed. The server refuses to start in this mode with an empty list. |
| `denylist` | Every host except those matching `AUDIOLLA_FETCH_HOSTS` is allowed. |

A host pattern is an exact host name or `*.` plus a suffix. `*.s3.amazonaws.com` matches `bucket.s3.amazonaws.com` but not `s3.amazonaws.com` itself, which needs its own entry.

These checks apply in every mode, to downloads and uploads alike ([src/audiolla/fetch.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/fetch.py)):

- The scheme must be in `AUDIOLLA_FETCH_SCHEMES` (`https` only by default).
- Unless `AUDIOLLA_FETCH_ALLOW_PRIVATE=true`, the host is resolved first and refused if any address is private, loopback, link-local, multicast, reserved or unspecified. This keeps a caller from pointing the server at cloud metadata endpoints or your LAN.
- Redirects are not followed automatically. Each `Location` goes through the same checks, up to `AUDIOLLA_FETCH_MAX_REDIRECTS` hops.
- Each request has a timeout of `AUDIOLLA_FETCH_TIMEOUT` (30 seconds by default) and 10 seconds to connect.
- A download is streamed and aborted as soon as it passes `AUDIOLLA_MAX_UPLOAD_BYTES`.
- Every fetch and upload URL is logged at `INFO`, including its query string. Presigned URLs carry their signature in the query string, so treat the logs as sensitive.

`allowlist` is the mode to use. `denylist` lets callers reach any public host, and the address check runs before the request is made, so a DNS name that changes its answer between the check and the connection is not caught.
