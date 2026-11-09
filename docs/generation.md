---
title: "Music and SFX generation"
description: "Text-to-audio with Stable Audio Open, MusicGen, Riffusion and AudioLDM 2: endpoints, licences, length caps, sample rates and the MusicGen opt-in."
nav_order: 11
---

# Music and SFX generation

Five text-to-audio engines turn a prompt into a loop, a short instrumental or a sound effect. Each has its own endpoint under `/v1/audio/generate/`. They differ in licence, length cap, sound and memory use, so pick by what you need to ship.

The generators exist only in the CUDA image (`psyb0t/audiolla:latest-cuda`). The CPU image's registry does not list them, so a request there returns 404 `unknown engine`. See [Deployment](deployment.md) for running the CUDA image and [Engines](engines.md) for the registries.

Generation has no input file. The body is a prompt plus the usual output fields: `output_path` or `output_url`, or `async_job` (see [Getting started](getting-started.md#input-and-output) and [Async jobs and webhooks](jobs.md)). Generation takes a while, especially the first call, so async jobs are a good fit.

## Examples

```bash
# Stable Audio Open 1.0: 47 s cap, instrumental, good for loops and SFX
curl -X POST http://localhost:8000/v1/audio/generate/stable-audio-open \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "130 bpm tech house drum loop, punchy kick, crisp hats, no vocals",
    "duration_sec": 10,
    "seed": 42,
    "output_path": "out/loop.wav"
  }'
# -> {"path":"out/loop.wav","size":...,"engine":"stable-audio-open","prompt":"130 bpm tech house ...","duration_sec":10.0,"seed":42,"output_format":"wav"}
curl -o loop.wav http://localhost:8000/v1/files/out/loop.wav

# MusicGen 300M: 30 s cap, instrumental, CC-BY-NC (needs the opt-in below)
curl -X POST http://localhost:8000/v1/audio/generate/musicgen-small \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "lo-fi hip-hop beat with vinyl crackle, 90 bpm",
    "duration_sec": 15,
    "output_path": "out/beat.wav"
  }'

# Riffusion: spectrogram image turned into audio with Griffin-Lim, about 5 s, lo-fi
curl -X POST http://localhost:8000/v1/audio/generate/riffusion \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"ambient drone with metallic resonance","output_path":"out/drone.wav"}'

# AudioLDM 2: general SFX, CC-BY 4.0, no opt-in
curl -X POST http://localhost:8000/v1/audio/generate/audioldm2 \
  -H 'Content-Type: application/json' \
  -d '{
    "prompt": "heavy rain on a metal roof with distant thunder",
    "duration_sec": 10,
    "num_inference_steps": 50,
    "output_path": "out/rain.wav"
  }'
```

## Engines

| Endpoint | Model | Licence | Max `duration_sec` | Output | VRAM (fp16, approximate) |
| --- | --- | --- | --- | --- | --- |
| `/v1/audio/generate/stable-audio-open` | `stabilityai/stable-audio-open-1.0` | Stability AI Community Licence (commercial use allowed below its revenue threshold) | 47 | 44.1 kHz stereo. Loops, riffs, ambient textures, SFX, drum beats; no vocals | about 12 GB |
| `/v1/audio/generate/musicgen-small` | `facebook/musicgen-small` (300M) | CC-BY-NC 4.0, non-commercial; needs `AUDIOLLA_ENABLE_NONCOMMERCIAL` | 30 | 32 kHz mono, instrumental | about 3 GB |
| `/v1/audio/generate/musicgen-medium` | `facebook/musicgen-medium` (1.5B) | CC-BY-NC 4.0, same opt-in | 30 | 32 kHz mono, instrumental, better than small | about 6 GB |
| `/v1/audio/generate/riffusion` | `riffusion/riffusion-model-v1` | CreativeML OpenRAIL-M (commercial use allowed within its use restrictions) | 30, but one pass yields about 5 s | 22.05 kHz mono, lo-fi and loop-friendly | about 3 GB |
| `/v1/audio/generate/audioldm2` | `cvssp/audioldm2` | CC-BY 4.0 (commercial use allowed, no opt-in) | 30 | 16 kHz mono. Ambience, foley, animal, mechanical and impact sounds | about 8 to 10 GB with CPU offload |

The VRAM figures come from the engine notes in [`src/audiolla/engines/music_gen.py`](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/engines/music_gen.py), not from a benchmark. Loading a generator unloads every other loaded engine first.

Read each model's licence before you use the output commercially. AudioLDM 2 is the one generator here that allows commercial use with no flag and no revenue threshold.

## Request fields

All five endpoints take:

| Field | Default | Meaning |
| --- | --- | --- |
| `prompt` | required | Text description, at least one character. |
| `duration_sec` | `10.0` | Length in seconds. Must be above zero and at most the engine's cap, or the request fails with 400. |
| `seed` | none | Integer seed for repeatable output. |
| `output_format` | `wav` | `wav`, `mp3`, `flac`, `opus`, `aac` or `pcm`. |
| `output_path`, `output_url`, `async_job`, `webhook_url` | | Output and job fields, as on every audio-producing endpoint. |

Engine-specific fields:

- `stable-audio-open` and `audioldm2` take `num_inference_steps` (1 to 500; default 100 for Stable Audio Open, 200 for AudioLDM 2). Fewer steps run faster and sound worse. AudioLDM 2 at 200 steps is slow; 50 steps cuts the time to roughly a quarter.
- `musicgen-small` and `musicgen-medium` accept `lyrics` for API uniformity and ignore it, since MusicGen is instrumental only.
- Riffusion always runs 50 steps. If `duration_sec` is shorter than what one pass produces, the output is trimmed; if it is longer, you still get about 5 s.
- The spec lists a `negative_prompt` field for Stable Audio Open and AudioLDM 2, but the engines use a fixed negative prompt and ignore the field.

The JSON response carries `engine`, `prompt`, `duration_sec`, `seed` and `output_format` next to `path` or `url` and `size`.

## MusicGen licence opt-in

MusicGen weights are CC-BY-NC 4.0. The engine code ships in the image, but it refuses to load the model unless the server's environment has `AUDIOLLA_ENABLE_NONCOMMERCIAL` set to `1`, `true`, `yes` or `on`. Without it, the request fails with 400 and a message pointing at the licence. Read the [MusicGen weights licence](https://github.com/facebookresearch/audiocraft/blob/main/LICENSE_weights) before you opt in.

```bash
docker run --rm --gpus all \
  -v $HOME/.audiolla-data:/data \
  -e AUDIOLLA_ENABLE_NONCOMMERCIAL=1 \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest-cuda
```

## Weights, tokens and devices

Model weights download from Hugging Face on the first call into `HF_HOME` (`/data/hf` in the images), so mount `/data` to keep them. The first call takes several minutes; later calls only run inference.

Stable Audio Open is a gated repository on Hugging Face: accept its terms with your account and start the container with `HF_TOKEN` or `HUGGINGFACE_TOKEN` (the entrypoint mirrors one into the other). See [Configuration](configuration.md).

Each generator loads on CUDA when a GPU is visible and falls back to CPU at fp32 when it is not. The generate endpoints do not check the `cuda_only` flag in the registry, so the CUDA image started without `--gpus all` will try to generate on the CPU, very slowly, instead of refusing.

## Not included

These generators were looked at and left out:

- ACE-Step v1 (Apache 2.0, full songs with vocals): needs `AceStepPipeline` from diffusers 0.38 or later, which needs a pre-release `safetensors`. That does not pass the hash-locked dependency gate; the images pin diffusers 0.32.2 and safetensors 0.7.0.
- DiffRhythm (Apache 2.0): a research repository with no package release.
- Stable Audio Open Small: needs `stable-audio-tools`, which requires Python below 3.11. The images run Python 3.12.
- TangoFlux: git-only install, no PyPI package.
- AudioGen (Meta, CC-BY-NC): `audiocraft` 1.3.0 pins `transformers` 4.31.0 or older, and the images use 4.51.3.
- YuE 7B (Apache 2.0, full songs with vocals): needs 16 to 24 GB of VRAM at fp16.
- MAGNeT and JASCO: CC-BY-NC weights, the same family as MusicGen.
