---
title: "Home"
description: "audiolla runs stem separation, mastering, analysis, restoration, speech, MIDI and music generation engines behind one REST and MCP API in Docker."
nav_order: 1
permalink: /
seo:
  type: WebSite
---

# audiolla

audiolla is one Docker image that wraps a pile of open-source audio tools (Demucs, UVR, matchering, pedalboard, librosa, SoX, ffmpeg, basic-pitch, DeepFilterNet, silero-vad, pyannote, CLAP, AST, fluidsynth and five text-to-audio models) behind a single HTTP API on port 8000. You stage a file, POST a JSON body, and get audio, MIDI, images or JSON back; LLM agents get the same tools over MCP at `/v1/mcp`.

There is no account, no cloud and no per-minute bill. It runs on your machine, on a CPU or an NVIDIA GPU.

## Install

```bash
# CPU
docker run --rm -it \
  -v $HOME/.audiolla-data:/data \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest

# NVIDIA GPU
docker run --rm -it --gpus all \
  -v $HOME/.audiolla-data:/data \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest-cuda
```

Then check it is up:

```bash
curl http://localhost:8000/healthz
```

The [getting started](getting-started.md) page walks through the first real request.

## Where to read

| You want to | Read |
| --- | --- |
| Run your first request end to end | [Getting started](getting-started.md) |
| Pick an image, mount data, use a GPU, upgrade | [Deployment](deployment.md) |
| Look up an environment variable | [Configuration](configuration.md) |
| Upload, download and expire files, or use S3-style URLs | [Files and remote URLs](files.md) |
| Split stems, remix, remove reverb, echo, noise or hum | [Separation and restoration](separation-and-restoration.md) |
| Master, compress, EQ, pan, add reverb or effects | [Mastering, dynamics and effects](mastering-and-effects.md) |
| Get BPM, key, chords, loudness, tags, embeddings | [Analysis](analysis.md) |
| Enhance speech, detect voice, find speakers | [Speech](speech.md) |
| Trim, mix, concat, stretch, pitch, convert, tag, visualize | [Editing, time and pitch](editing.md) |
| Generate music or sound effects from a prompt | [Music and SFX generation](generation.md) |
| Transcribe audio to MIDI, compose, render MIDI | [MIDI](midi.md) |
| Chain steps server-side or run many ops at once | [Presets, pipelines and batch](workflows.md) |
| Run long work in the background with webhooks | [Async jobs and webhooks](jobs.md) |
| See every engine, what image it ships in, its license | [Engines](engines.md) |
| Read every endpoint and field | [REST API reference](api.md) |
| Connect an LLM agent | [MCP server](mcp.md) and [Agent integrations](agent-integrations.md) |
| Put it on a network safely | [Security](security.md) |
| Fix an error | [Troubleshooting](troubleshooting.md) |
| Understand how the pieces fit | [Architecture](architecture.md) |
| Build, test or change the code | [Development](development.md) |

## Images

| Tag | Device | Engines |
| --- | --- | --- |
| `psyb0t/audiolla:latest`, `psyb0t/audiolla:vX.Y.Z` | CPU | 27 |
| `psyb0t/audiolla:latest-cuda`, `psyb0t/audiolla:vX.Y.Z-cuda` | NVIDIA GPU (CUDA 12.4 build of Torch) | 35 |

Both are `linux/amd64`. The CUDA image adds the larger Demucs variants and the five generators; the [engines](engines.md) page has the full list.

## License

audiolla itself is [WTFPL](https://github.com/psyb0t/docker-audiolla/blob/main/LICENSE). The images bundle third-party code under its own licenses, including GPL v3 (matchering, pedalboard); [THIRD_PARTY.md](https://github.com/psyb0t/docker-audiolla/blob/main/THIRD_PARTY.md) lists them. Model weights are not in the images: engines download them at startup or first use, under each model's own license, and some of those are non-commercial (MusicGen). The [engines](engines.md) page has the per-model terms.
