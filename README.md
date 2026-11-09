# audiolla

[![CI](https://github.com/psyb0t/docker-audiolla/actions/workflows/pipeline.yml/badge.svg?branch=main)](https://github.com/psyb0t/docker-audiolla/actions/workflows/pipeline.yml)
[![version](https://raw.githubusercontent.com/psyb0t/docker-audiolla/badges/version.svg)](https://github.com/psyb0t/docker-audiolla/releases)
[![license](https://raw.githubusercontent.com/psyb0t/docker-audiolla/badges/license.svg)](LICENSE)
[![Docker Pulls](https://img.shields.io/docker/pulls/psyb0t/audiolla?style=flat-square)](https://hub.docker.com/r/psyb0t/audiolla)

**Thirty-five audio engines. One port. Zero cloud. Fire-and-forget async jobs. Webhooks.**

You needed Demucs for stems. Then librosa for BPM and key. Then basic-pitch for MIDI transcription. Then pyannote for speaker diarization. Then DeepFilterNet for speech enhancement. Then you spent three days debugging Python version conflicts and now you hate everything.

audiolla is what happens when you stop doing that.

Every audio processing tool worth using, wrapped in one HTTP API, running in one Docker container. Stage a file, POST a JSON body, get audio, JSON or MIDI back. Drive it from curl, shell scripts, Python notebooks, Makefiles, or point an LLM agent at the MCP endpoint and let it rip.

No account. No subscription. No per-minute billing. No vendor lock-in. `docker run` and you're done.

## Contents

- [What's in the box](#whats-in-the-box)
- [Run it](#run-it)
- [Quick start](#quick-start)
- [Documentation](#documentation)
- [Agents and MCP](#agents-and-mcp)
- [Build and dev](#build-and-dev)
- [Sponsor](#sponsor)
- [License](#license)

## What's in the box

| | |
|--|--|
| **Stems and restoration** | Demucs (4 and 6 stems), UVR BS-Roformer and MelBand Roformer (de-reverb, de-echo, de-noise, karaoke, vocals), HPSS, remix, declip, dehum, spectral noise reduction |
| **Mastering and effects** | matchering reference mastering, pedalboard chains, 24 pedalboard effects, SoX transforms, multiband compression, transient shaping, de-essing, sidechain ducking, convolution reverb, EQ, pan, stereo width, mid/side |
| **Analysis** | BPM, key, chords, LUFS, loudness curves, beats, onsets, melody, segments, silence, fingerprints, AudioSet tags, CLAP embeddings and zero-shot labels, clipping, stereo field, loop points, DJ prep |
| **Speech** | DeepFilterNet enhancement, silero-vad voice activity, pyannote speaker diarization |
| **Editing** | Trim, mix, concat, speed, convert, fade, reverse, loop, split, beat slicing, thumbnails, time-stretch, pitch shift, BPM and key matching, tags, spectrogram and waveform images, spectrum videos |
| **MIDI** | basic-pitch audio to MIDI, compose from JSON, drum patterns, chords to MIDI, inspect, transform, quantize, humanize, fluidsynth rendering |
| **Generation** (CUDA image) | Stable Audio Open, MusicGen small and medium, Riffusion, AudioLDM 2 |
| **Workflows** | Curated YAML presets, ad-hoc server-side pipelines, batch calls, async jobs with webhooks |
| **Agents** | MCP server at `/v1/mcp` with 82 tools, plus a skill and plugins for Claude Code, Codex and OpenClaw |

## Run it

```bash
# no GPU
docker run --rm -it \
  -v $HOME/.audiolla-data:/data \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest

# GPU
docker run --rm -it --gpus all \
  -v $HOME/.audiolla-data:/data \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest-cuda
```

Demucs weights download at container startup for the enabled Demucs engines and cache in `/data/torch_cache/`. Other models download on first use into `/data`. Same `-v` mount next time and they're already there. The CPU image carries 27 engines; the CUDA image adds the bigger Demucs variants and the generators for 35.

Going beyond localhost? Set `AUDIOLLA_AUTH_TOKEN` first and read the [security page](https://psyb0t.github.io/docker-audiolla/security/).

## Quick start

Stage the input once, then reference it by path. Every audio endpoint takes a JSON body.

```bash
# stage your input file
curl -X PUT --data-binary @song.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/song.wav

# rip the vocals out of a track
curl -X POST http://localhost:8000/v1/audio/separate \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/song.wav","engine":"htdemucs","stems":["vocals"],"output_path":"out/vocals.wav"}'
curl -o vocals.wav http://localhost:8000/v1/files/out/vocals.wav

# what key is it in? what are the chords?
curl -X POST http://localhost:8000/v1/audio/chords \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/song.wav"}'

# transcribe that vocal melody to MIDI, then render it back through a SoundFont
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"out/vocals.wav","output_path":"out/melody.mid"}'
curl -X POST http://localhost:8000/v1/midi/render \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"out/melody.mid","output_path":"out/rendered.wav"}'
```

Audio in. MIDI out. Chords detected. Re-synthesized. No Python environment to set up. No API keys. Just HTTP.

## Documentation

The full documentation lives at **[psyb0t.github.io/docker-audiolla](https://psyb0t.github.io/docker-audiolla/)**.

| Section | What's there |
| --- | --- |
| [Getting started](https://psyb0t.github.io/docker-audiolla/getting-started/) | First request end to end, and the input and output rules every endpoint shares |
| [Deployment](https://psyb0t.github.io/docker-audiolla/deployment/) | Images and tags, the `/data` layout, GPUs, Hugging Face tokens, upgrades |
| [Configuration](https://psyb0t.github.io/docker-audiolla/configuration/) | Every environment variable |
| [Files and remote URLs](https://psyb0t.github.io/docker-audiolla/files/) | Staging, retention, S3-style presigned URLs, the fetch policy |
| [Engines](https://psyb0t.github.io/docker-audiolla/engines/) | Every engine, which image has it, model licenses, loading and unloading |
| [REST API reference](https://psyb0t.github.io/docker-audiolla/api/) | Every endpoint and field, from [openapi.yaml](openapi.yaml) |
| [MCP server](https://psyb0t.github.io/docker-audiolla/mcp/) | The 82 MCP tools and how to connect |
| [Security](https://psyb0t.github.io/docker-audiolla/security/) | Auth, outbound requests, logs, what to set before exposing it |
| [Troubleshooting](https://psyb0t.github.io/docker-audiolla/troubleshooting/) | Exact error messages, causes and fixes |
| [Development](https://psyb0t.github.io/docker-audiolla/development/) | Makefile, tests, code generation, dependency locks, CI |

Feature guides with curl examples: [separation and restoration](https://psyb0t.github.io/docker-audiolla/separation-and-restoration/), [mastering and effects](https://psyb0t.github.io/docker-audiolla/mastering-and-effects/), [analysis](https://psyb0t.github.io/docker-audiolla/analysis/), [speech](https://psyb0t.github.io/docker-audiolla/speech/), [editing](https://psyb0t.github.io/docker-audiolla/editing/), [generation](https://psyb0t.github.io/docker-audiolla/generation/), [MIDI](https://psyb0t.github.io/docker-audiolla/midi/), [presets and pipelines](https://psyb0t.github.io/docker-audiolla/workflows/), [async jobs](https://psyb0t.github.io/docker-audiolla/jobs/).

## Agents and MCP

Point any MCP client that speaks Streamable HTTP at `http://localhost:8000/v1/mcp` (with `Authorization: Bearer <token>` if auth is on) and it gets the audio toolset as callable tools. For Claude Code, Codex and OpenClaw there is a ready skill and plugin:

```bash
claude plugin marketplace add psyb0t/agents
claude plugin install audiolla@psyb0t
```

The [agent integrations page](https://psyb0t.github.io/docker-audiolla/agent-integrations/) covers Codex, OpenClaw and the stdio bridge. The [skill](.agents/skills/audiolla) also works in any agent that reads `.agents/skills/`, such as [peen](https://github.com/psyb0t/peen).

## Build and dev

```bash
make build        # CPU image
make build-cuda   # CUDA image
make lint         # flake8 + mypy in the dev container
make test         # offline unit tests in the dev container
make generate     # regenerate src/audiolla/schema/ from openapi.yaml
make docs         # build the docs site into .testing/docs-site
make help         # everything else
```

The host needs `docker`, `make` and `git`. [Development](https://psyb0t.github.io/docker-audiolla/development/) has the details, and [CHANGELOG.md](CHANGELOG.md) has the release history.

## Sponsor

<a href="https://www.buymeacoffee.com/psyb0t"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-blue.png" alt="Buy Me a Coffee" height="60" width="217"></a>

## License

[WTFPL](LICENSE).

matchering and pedalboard are GPL v3. Fine for self-hosted use. Distributing the image as a product needs a GPL compliance review. [THIRD_PARTY.md](THIRD_PARTY.md) lists the bundled third-party components. Model weights download at runtime under their own licenses, and MusicGen's are non-commercial; the [engines page](https://psyb0t.github.io/docker-audiolla/engines/#weights-and-licenses) has the per-model terms.
