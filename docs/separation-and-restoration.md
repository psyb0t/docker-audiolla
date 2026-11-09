---
title: "Separation and restoration"
description: "Split stems with Demucs or UVR, remix them, split harmonic from percussive, and remove reverb, echo, noise, clipping and mains hum."
nav_order: 6
---

# Separation and restoration

This page covers the endpoints that take a mix apart or clean a recording up: stem separation (`/v1/audio/separate`), remixing stems (`/v1/audio/remix`), harmonic/percussive splitting (`/v1/audio/separate/hpss`), UVR restoration (`/v1/audio/restore/{engine}`), noise reduction (`/v1/audio/noise-reduce/{engine}`) and declip/dehum repair (`/v1/audio/repair`).

Every one of them takes a JSON body with `file_path` or `file_url` and writes its result to `output_path` or `output_url` (or runs as an async job). The full contract is in [Getting started](getting-started.md#input-and-output), async jobs are in [Async jobs and webhooks](jobs.md), and staging files is in [Files and remote URLs](files.md). Field-level schemas live in the [REST API reference](api.md). The examples below assume the input is already staged:

```bash
curl -X PUT --data-binary @track.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/track.wav
```

## Split stems

`POST /v1/audio/separate` runs a stem-separation engine. `engine` picks the model (default `htdemucs`), and `stems` picks which stems come back. Ask for one stem and you get one audio file; ask for several, or leave `stems` empty to get every stem the engine has, and you get a ZIP with one file per stem.

```bash
# vocals only
curl -X POST http://localhost:8000/v1/audio/separate \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "engine": "htdemucs",
    "stems": ["vocals"],
    "output_path": "out/vocals.wav"
  }'
# -> {"path":"out/vocals.wav","size":...,"engine":"htdemucs","stem":"vocals","output_format":"wav"}
curl -o vocals.wav http://localhost:8000/v1/files/out/vocals.wav

# all 4 stems as a ZIP
curl -X POST http://localhost:8000/v1/audio/separate \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","engine":"htdemucs","output_path":"out/stems.zip"}'
# -> {"path":"out/stems.zip","size":...,"engine":"htdemucs","output_format":"wav","stems":["drums","bass","other","vocals"]}
curl -o stems.zip http://localhost:8000/v1/files/out/stems.zip
```

Engines and their stem names (from `engines.json`):

| Engine | Stems | Image |
| --- | --- | --- |
| `htdemucs` | `drums`, `bass`, `other`, `vocals` | CPU and CUDA |
| `htdemucs_ft` | `drums`, `bass`, `other`, `vocals` (fine-tuned weights, slower) | CUDA only |
| `htdemucs_6s` | adds `guitar` and `piano` to the four above | CUDA only |
| `mdx_extra` | `drums`, `bass`, `other`, `vocals` | CUDA only |
| `uvr-vocal-bsr` | `Vocals`, `Instrumental` (BS-Roformer) | CPU and CUDA |
| `uvr-karaoke` | `Vocals`, `Instrumental` (MelBand Roformer karaoke model, lead vocal removed from the instrumental) | CPU and CUDA |

The UVR stem names are capitalized, so ask for `"stems":["Instrumental"]`, not `"instrumental"`. A stem the engine does not have is a 400 that lists the available ones.

The CPU image ships only `htdemucs` from the Demucs family. On that image `htdemucs_ft`, `htdemucs_6s` and `mdx_extra` are not in the registry at all, so asking for them returns 404 `unknown engine`. `htdemucs_ft` is also flagged `cuda_only`: if the CUDA image runs with `AUDIOLLA_DEVICE=cpu`, the request is rejected with 400. See [Engines](engines.md) for the full list and [Configuration](configuration.md) for `AUDIOLLA_DEVICE`.

Each Demucs variant is a separate checkpoint. The entrypoint downloads every enabled variant into `/data/torch_cache/` at startup, so the first separation request does not wait for a download.

## Remix stems

`POST /v1/audio/remix` separates the track, applies a gain or mute per stem, and mixes the stems back down into one file. Use it for "vocals down 6 dB" or "drums only" without handling stems yourself.

`engine` defaults to `htdemucs`. `stem_mix` maps stem names to numbers. The handler reads each number like this:

- `0` mutes the stem.
- A value above 0 and up to 1 is a linear gain: `1.0` keeps the stem as is, `0.5` is about -6 dB.
- Any other number (negative, or above 1) is a gain in dB: `-12` lowers the stem by 12 dB, `3` raises it by 3 dB.

Stems you leave out of `stem_mix` stay at unity gain. If every stem ends up muted, the request fails with 400 `all stems are muted`.

```bash
# karaoke-style: mute vocals, keep everything else
curl -X POST http://localhost:8000/v1/audio/remix \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "stem_mix": {"vocals": 0},
    "output_path": "out/no_vocals.wav"
  }'
# -> {"path":"out/no_vocals.wav","size":...,"engine":"htdemucs","stems":["drums","bass","other","vocals"]}

# drums only, bass pulled down 6 dB
curl -X POST http://localhost:8000/v1/audio/remix \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "stem_mix": {"drums": 1.0, "bass": -6, "vocals": 0, "other": 0},
    "output_path": "out/rhythm.wav"
  }'
```

Note the `stems` list in the response is the set of stems the engine produced, including muted ones.

## Harmonic/percussive split

`POST /v1/audio/separate/hpss` splits audio into a harmonic part (tonal content: pitched instruments, pads) and a percussive part (transients: drums, percussion) with librosa's median-filter HPSS. No model, no GPU. The result is always a ZIP with `harmonic.<format>` and `percussive.<format>`.

```bash
# both stems in a ZIP
curl -X POST http://localhost:8000/v1/audio/separate/hpss \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","output_path":"out/stems.zip"}'
# -> {"path":"out/stems.zip","size":...,"stems":["harmonic","percussive"],"output_format":"wav"}
curl -o stems.zip http://localhost:8000/v1/files/out/stems.zip

# wider margin, harder separation
curl -X POST http://localhost:8000/v1/audio/separate/hpss \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","margin":3.0,"output_path":"out/stems.zip"}'
```

Parameters: `margin` (default `1.0`; higher separates harder, and librosa rejects values below 1.0), `kernel_size` (default `31`, the median filter width), `output_format` (default `wav`).

## De-reverb, de-echo, de-noise

`POST /v1/audio/restore/{engine}` runs a UVR restoration model and returns the cleaned audio. The engines (all in both images):

| Engine | Model | Removes |
| --- | --- | --- |
| `uvr-dereverb` | BS-Roformer de-reverb | room reverb |
| `uvr-deecho` | VR Architecture de-echo, normal and aggressive models | echo |
| `uvr-denoise` | MelBand Roformer de-noise | broadband background noise |

```bash
# remove room reverb
curl -X POST http://localhost:8000/v1/audio/restore/uvr-dereverb \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","output_path":"out/dry.wav"}'

# remove echo, normal mode
curl -X POST http://localhost:8000/v1/audio/restore/uvr-deecho \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","output_path":"out/noecho.wav"}'

# remove echo, aggressive mode (same engine, harder suppression)
curl -X POST http://localhost:8000/v1/audio/restore/uvr-deecho \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","aggressive":true,"output_path":"out/noecho.wav"}'
# -> {"path":"out/noecho.wav","size":...,"engine":"uvr-deecho","aggressive":true,"output_format":"wav"}

# remove broadband background noise
curl -X POST http://localhost:8000/v1/audio/restore/uvr-denoise \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","output_path":"out/clean.wav"}'
```

`aggressive` (default `false`) only works on `uvr-deecho`, the one engine with a second model configured. On any other engine it fails with 400 `has no aggressive model configured`. The endpoint accepts any UVR slug, including `uvr-karaoke` and `uvr-vocal-bsr`, but those are separation models; use them through `/v1/audio/separate`. A slug that is not a UVR engine gets 400, and one that is not configured gets 404.

UVR model files are cached in `AUDIOLLA_UVR_MODELS_DIR` (default `/data/uvr_models`).

## Noise reduction

`POST /v1/audio/noise-reduce/{engine}` offers two kinds of noise reduction behind one path:

- `noise-reduce`: spectral noise reduction with the noisereduce library. DSP, no model download, no GPU.
- `uvr-denoise`: the UVR MelBand Roformer model, the same as `/v1/audio/restore/uvr-denoise`.

```bash
# DSP, non-stationary (adaptive) mode
curl -X POST http://localhost:8000/v1/audio/noise-reduce/noise-reduce \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav","output_path":"out/clean.wav"}'

# stationary mode: constant hum, hiss, fan noise
curl -X POST http://localhost:8000/v1/audio/noise-reduce/noise-reduce \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav","stationary":true,"output_path":"out/clean.wav"}'

# partial reduction, subtle noise floor cleanup
curl -X POST http://localhost:8000/v1/audio/noise-reduce/noise-reduce \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav","prop_decrease":0.5,"output_path":"out/clean.wav"}'
# -> {"path":"out/clean.wav","size":...,"engine":"noise-reduce","stationary":false,"prop_decrease":0.5,"output_format":"wav"}

# ML model
curl -X POST http://localhost:8000/v1/audio/noise-reduce/uvr-denoise \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav","output_path":"out/clean.wav"}'
```

The DSP parameters only apply to `noise-reduce`: `stationary` (default `false`) and `prop_decrease` (default `1.0`, how much of the estimated noise to remove; outside 0.0 to 1.0 is a 400). The ML engine ignores both.

## Repair

`POST /v1/audio/repair` fixes clipped peaks and removes mains hum.

- Declip finds samples at or above 0.999 of full scale and replaces them by linear interpolation from the unclipped samples around them.
- Dehum applies notch filters at `hum_freq` and its next three harmonics (2x, 3x and 4x).

```bash
# declip only (default)
curl -X POST http://localhost:8000/v1/audio/repair \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/overdriven.wav","output_path":"out/repaired.wav"}'
# -> {"path":"out/repaired.wav","size":...,"declip":true,"dehum":false,"hum_freq":50.0}

# remove 60 Hz hum (North American mains)
curl -X POST http://localhost:8000/v1/audio/repair \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/recording.wav",
    "declip": false,
    "dehum": true,
    "hum_freq": 60.0,
    "output_path": "out/clean.wav"
  }'

# both, on a mic recording with 50 Hz hum, staged as FLAC
curl -X POST http://localhost:8000/v1/audio/repair \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/problem_track.wav",
    "declip": true,
    "dehum": true,
    "hum_freq": 50.0,
    "output_format": "flac",
    "output_path": "out/repaired.flac"
  }'
```

Parameters: `declip` (default `true`), `dehum` (default `false`), `hum_freq` (Hz, default `50.0`, must be between 40 and 80). Turning both `declip` and `dehum` off is a 400. Repair needs no engine; it runs in the server process with numpy and scipy.
