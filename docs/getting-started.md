---
title: "Getting started"
description: "Start the audiolla container, stage an audio file, split vocals, detect chords, transcribe to MIDI and download the results with curl."
nav_order: 2
---

# Getting started

This page goes from nothing to a separated vocal, a chord chart and a MIDI file. It uses the CPU image and `curl`; the CUDA image works the same way with `--gpus all`.

## Start the server

```bash
mkdir -p $HOME/.audiolla-data

docker run --rm -it \
  -v $HOME/.audiolla-data:/data \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest
```

On start the entrypoint downloads the Demucs checkpoints for every enabled Demucs engine into `/data/torch_cache/` (on the CPU image that is only `htdemucs`). Other engines fetch their weights the first time you call them. Keep the same `-v` mount and nothing is downloaded twice. [Deployment](deployment.md) covers the GPU image, restricting engines and what lives under `/data`.

Wait for the health check:

```bash
curl http://localhost:8000/healthz
# -> {"ok":true,"device":"cpu","engines":["htdemucs","matchering",...]}
```

## Stage a file

Audio endpoints do not take uploads. You put the file in the server's staging area first, then refer to it by path. The body of `PUT /v1/files/{path}` is the raw file:

```bash
curl -X PUT --data-binary @song.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/song.wav
# -> {"path":"uploads/song.wav","size":...}
```

Staged files expire 24 hours after their last write by default. [Files and remote URLs](files.md) explains retention, listing and deleting.

## Split the vocals

```bash
curl -X POST http://localhost:8000/v1/audio/separate \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/song.wav",
    "engine": "htdemucs",
    "stems": ["vocals"],
    "output_path": "out/vocals.wav"
  }'
# -> {"path":"out/vocals.wav","size":...,"engine":"htdemucs","stem":"vocals","output_format":"wav"}

curl -o vocals.wav http://localhost:8000/v1/files/out/vocals.wav
```

## Detect key and chords

Analysis endpoints answer with JSON and need no output path:

```bash
curl -X POST http://localhost:8000/v1/audio/chords \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/song.wav"}'
# -> {"key":"F# minor","key_confidence":0.91,"chords":[{"chord":"F#m","start_sec":0.0,...},...]}
```

## Transcribe the vocal to MIDI and play it back

The separated vocal is already staged at `out/vocals.wav`, so the next calls read it directly:

```bash
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"out/vocals.wav","output_path":"out/melody.mid"}'

curl -X POST http://localhost:8000/v1/midi/render \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"out/melody.mid","output_path":"out/rendered.wav"}'

curl -o rendered.wav http://localhost:8000/v1/files/out/rendered.wav
```

`/v1/midi/render` uses the FluidR3_GM SoundFont shipped in both images.

## Input and output

Every audio endpoint takes an `application/json` body and the same input and output rules.

Input, exactly one of:

- `file_path`: a path in the staging area, as used with `PUT /v1/files/{path}`. A leading `/`, `/files/` or `/v1/files/` prefix is stripped, so `uploads/a.wav` and `/v1/files/uploads/a.wav` are the same file.
- `file_url`: an `http(s)` URL the server downloads. This is off until you set a fetch policy; see [remote URLs](files.md#remote-urls).

Sending neither or both gets a 400. Endpoints with a second input use the same either-or pair under another name: `reference_path` or `reference_url` for a mastering reference, `trigger_file_path` or `trigger_file_url` for a sidechain trigger, `ir_file_path` or `ir_file_url` for an impulse response. The [API reference](api.md) names them per endpoint.

Output, for endpoints that produce audio, MIDI, images or ZIP archives, exactly one of:

- `output_path`: the server writes the result into the staging area and answers `{"path": ..., "size": ..., ...}`. Download it with `GET /v1/files/{path}`. A result larger than `AUDIOLLA_MAX_UPLOAD_BYTES` gets a 413 instead.
- `output_url`: the server sends the result with an HTTP `PUT` to that URL, typically a presigned S3 upload URL, and answers `{"url": ..., "size": ..., ...}`. This needs the same fetch policy as `file_url`.

A synchronous call with neither, or any call with both, gets a 400. With `"async_job": true` both are optional: the result goes to `jobs/<job_id>.<ext>` in the staging area. [Async jobs](jobs.md) covers that path.

Endpoints that only measure (`/v1/audio/analyze`, `/v1/audio/loudness`, `/v1/audio/info`, `/v1/audio/chords` and the rest of the [analysis](analysis.md) page) return their JSON directly. Two MIDI endpoints, `/v1/midi/compose` and `/v1/midi/generate`, take the song spec as the body and the output options as query parameters; the [MIDI](midi.md) page explains them.

Audio results default to `wav`. Set `"output_format"` to `mp3`, `flac`, `opus`, `aac` or `pcm` on endpoints that accept it; an unsupported value gets a 415.

Errors are JSON: `{"detail": "..."}` with a 4xx or 5xx status. The [API reference](api.md) lists every field of every endpoint.

## Next steps

- Turn on auth before anything else can reach the port: [Security](security.md).
- Browse what the API can do from the [home page](index.md#where-to-read), or ask the server: `GET /v1/catalog` returns the endpoints grouped by category.
- Point an agent at `http://localhost:8000/v1/mcp`: [MCP server](mcp.md).
