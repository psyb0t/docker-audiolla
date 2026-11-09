---
title: "Engines"
description: "Every audiolla engine slug, which image ships it, what it wraps, model licenses, the engine registry format and how engines load and unload."
nav_order: 16
---

# Engines

An engine is one named backend, such as `htdemucs` or `librosa-analyze`. Engines that use model weights load them on first use, keep them in memory while busy and unload them when idle. Plain DSP work (trim, fade, EQ, mix, pan and similar) runs as functions in `src/audiolla/audio.py` and needs no engine at all.

The registry file decides which engines exist: the CPU image reads [engines-cpu.json](https://github.com/psyb0t/docker-audiolla/blob/main/engines-cpu.json) and the CUDA image reads [engines.json](https://github.com/psyb0t/docker-audiolla/blob/main/engines.json), both copied to `/app/engines.json`. `GET /v1/engines` lists the engines the running server has.

## Engine list

| Slug | CPU image | What it does |
| --- | --- | --- |
| `htdemucs` | yes | Demucs 4-stem separation: drums, bass, other, vocals. |
| `htdemucs_ft` | no | Same 4 stems with fine-tuned weights. Marked `cuda_only`: on a CUDA image running without a GPU, `/v1/audio/separate` rejects it with 400. |
| `htdemucs_6s` | no | 6 stems, adds guitar and piano. |
| `mdx_extra` | no | Demucs MDX variant, 4 stems. |
| `matchering` | yes | Reference mastering: matches EQ and loudness to a reference track. Backs `/v1/audio/master` with `mode=reference`. |
| `pedalboard-chain` | yes | Fixed mastering chains `transparent` and `loud`. Backs `/v1/audio/master` with `mode=chain`. |
| `librosa-analyze` | yes | BPM, key, loudness, spectral features, beats, onsets, melody, segments, loop points, thumbnails, pitch correction. |
| `sox-transform` | yes | SoX operation chain: gain, EQ, compand, reverb, pitch, tempo, rate, channels, trim, pad. |
| `fx-chain` | yes | Any chain of the allowed pedalboard effects. Backs `/v1/audio/fx`. |
| `midi-compose` | yes | Song spec to MIDI, MIDI inspect, transform, quantize, humanize and drum patterns. |
| `midi-render` | yes | MIDI to audio through fluidsynth and a SoundFont. |
| `silence-detect` | yes | Silent ranges via ffmpeg `silencedetect`, trimming, splitting on silence. |
| `ffmpeg-render` | yes | Spectrogram and waveform PNGs, animated spectrum videos. |
| `audio-fingerprint` | yes | Chromaprint fingerprint through `fpcalc`. |
| `uvr-dereverb` | yes | UVR BS-Roformer de-reverb. |
| `uvr-deecho` | yes | UVR VR Architecture de-echo, with an aggressive model for `aggressive=true`. |
| `uvr-denoise` | yes | UVR MelBand Roformer de-noise. |
| `uvr-karaoke` | yes | UVR MelBand Roformer karaoke split, stems `Vocals` and `Instrumental`, used through `/v1/audio/separate`. |
| `uvr-vocal-bsr` | yes | UVR BS-Roformer vocal and instrumental split, used through `/v1/audio/separate`. |
| `basic-pitch` | yes | Spotify basic-pitch polyphonic audio to MIDI (ONNX). |
| `deepfilter` | yes | DeepFilterNet DF3 speech and vocal enhancement. |
| `chord-detect` | yes | Key estimation and chord segmentation from chroma. |
| `silero-vad` | yes | silero-vad voice activity detection. |
| `pyannote` | yes | pyannote/speaker-diarization-3.1 speaker diarization. Needs a Hugging Face token. |
| `stretch` | yes | librosa time-stretch and pitch-shift. |
| `ast-tag` | yes | AudioSet tagging with MIT/ast-finetuned-audioset-10-10-0.4593. |
| `clap-embed` | yes | 512-dimension CLAP embeddings (laion/larger_clap_music_and_speech), similarity and zero-shot classification. |
| `hpss` | yes | librosa harmonic and percussive split. |
| `noise-reduce` | yes | noisereduce spectral noise reduction, stationary and non-stationary. |
| `metadata` | yes | Read and write tags with mutagen. |
| `stable-audio-open` | no | Stability AI Stable Audio Open 1.0 text to audio. |
| `musicgen-small` | no | Meta MusicGen 300M text to music. Non-commercial weights, opt-in. |
| `musicgen-medium` | no | Meta MusicGen 1.5B text to music. Non-commercial weights, opt-in. |
| `riffusion` | no | Riffusion v1 spectrogram diffusion. |
| `audioldm2` | no | AudioLDM 2 text to sound effects. |

The feature pages explain the request fields: [separation and restoration](separation-and-restoration.md), [mastering and effects](mastering-and-effects.md), [analysis](analysis.md), [speech](speech.md), [editing](editing.md), [generation](generation.md) and [MIDI](midi.md).

## Weights and licenses

| Engines | Weights come from | Stored in |
| --- | --- | --- |
| Demucs (`htdemucs*`, `mdx_extra`) | `dl.fbaipublicfiles.com`, downloaded by `entrypoint.sh` at startup | `/data/torch_cache/` |
| `uvr-*` | the audio-separator model repository, on first use | `/data/uvr_models/` |
| `ast-tag`, `clap-embed`, `pyannote`, generators | Hugging Face, on first use | `/data/hf/` |
| `basic-pitch`, `silero-vad`, `deepfilter` | shipped with or fetched by their Python packages | the package or its own cache |

The generators carry model licenses you have to respect yourself:

| Engine | Model license |
| --- | --- |
| `stable-audio-open` | Stability AI Community License (gated on Hugging Face) |
| `musicgen-small`, `musicgen-medium` | CC-BY-NC 4.0, enabled only with `AUDIOLLA_ENABLE_NONCOMMERCIAL=1` |
| `riffusion` | CreativeML OpenRAIL-M |
| `audioldm2` | CC-BY 4.0 |

matchering and pedalboard are GPL v3 Python packages inside the images; [THIRD_PARTY.md](https://github.com/psyb0t/docker-audiolla/blob/main/THIRD_PARTY.md) lists the bundled third-party code.

Torch 2.5.1 is affected by [CVE-2025-32434](https://github.com/pytorch/pytorch/security/advisories/GHSA-53q9-r3pm-6pq6). Use model files from the sources above only, including anything you place in the cache directories yourself.

## Which endpoints need which engine

An endpoint whose engine is not enabled answers 404 with `<slug> engine not configured` (or `unknown engine '<slug>'` when the engine is a path or body parameter). This table is read from the handlers in [server.py](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/server.py).

| Endpoint | Engine |
| --- | --- |
| `/v1/audio/separate`, `/v1/audio/remix` | the `engine` field: a Demucs or separation-capable UVR slug |
| `/v1/audio/master` | `matchering` (reference mode) or `pedalboard-chain` (chain mode) |
| `/v1/audio/analyze`, `/v1/audio/loudness`, `/v1/audio/normalize`, `/v1/audio/beats`, `/v1/audio/onsets`, `/v1/audio/melody`, `/v1/audio/segments`, `/v1/audio/beat-slice`, `/v1/audio/pitch-correct`, `/v1/audio/loop-point`, `/v1/audio/thumbnail` | `librosa-analyze` |
| `/v1/audio/bpm-match` | `librosa-analyze` and `stretch` |
| `/v1/audio/key-match` | `chord-detect` and `stretch` |
| `/v1/audio/dj-prep` | `librosa-analyze` and `chord-detect` |
| `/v1/audio/chords`, `/v1/audio/chords-to-midi` | `chord-detect` |
| `/v1/audio/stretch` | `stretch` |
| `/v1/audio/transform` | `sox-transform` |
| `/v1/audio/fx` | `fx-chain` |
| `/v1/audio/silence`, `/v1/audio/split` | `silence-detect` |
| `/v1/audio/visualize/*` | `ffmpeg-render` |
| `/v1/audio/fingerprint` | `audio-fingerprint` |
| `/v1/audio/restore/{engine}` | a `uvr-*` slug in the path |
| `/v1/audio/noise-reduce/{engine}` | `noise-reduce` or a `uvr-*` slug in the path |
| `/v1/audio/enhance/{engine}` | `deepfilter` |
| `/v1/audio/to_midi/{engine}` | `basic-pitch` |
| `/v1/audio/vad` | `silero-vad` |
| `/v1/audio/diarize/{engine}` | `pyannote` |
| `/v1/audio/tag` | `ast-tag` |
| `/v1/audio/embed`, `/v1/audio/similar`, `/v1/audio/classify` | `clap-embed` |
| `/v1/audio/separate/hpss` | `hpss` |
| `/v1/audio/metadata` | `metadata` |
| `/v1/audio/generate/<slug>` | the generator with that slug |
| `/v1/midi/compose`, `/v1/midi/inspect`, `/v1/midi/transform`, `/v1/midi/quantize`, `/v1/midi/humanize`, `/v1/midi/drum` | `midi-compose` |
| `/v1/midi/render` | `midi-render` |
| `/v1/midi/generate` | `midi-compose` and `midi-render` |
| `/v1/batch` | `librosa-analyze` for its `normalize` op only |

Everything else (`info`, `trim`, `mix`, `concat`, `speed`, `convert`, `fade`, `reverse`, `loop`, `stereo-width`, `pan`, `eq`, `sidechain-duck`, `clip-detect`, `mid-side`, `conv-reverb`, `transient`, `multiband-compress`, `loudness/curve`, `repair`, `deess`, `stereo-field`) runs without an engine and works with any `AUDIOLLA_ENABLED_ENGINES` setting. Presets and pipelines need whatever engines their steps use.

## Loading and unloading

- **Lazy load.** An engine loads its weights the first time a request needs it, in a worker thread, behind a per-engine lock, so two concurrent first requests load once.
- **Preload.** `AUDIOLLA_PRELOAD=slug,slug` loads those engines during startup. A failed preload is logged and the server starts anyway.
- **Idle unload.** A sweeper checks every `AUDIOLLA_SWEEPER_INTERVAL` seconds (default 60) and unloads engines idle for `AUDIOLLA_ENGINE_TTL` (default 600 seconds). `AUDIOLLA_ENGINE_TTL=0` turns idle unloading off.
- **Sibling eviction.** Before the heavy model calls (`/v1/audio/separate`, `/v1/audio/master`, `/v1/audio/to_midi/*`, `/v1/audio/enhance/*`, `/v1/audio/generate/*`, `/v1/audio/remix`), the server unloads every other loaded engine to free GPU and system memory. A request that needs a different engine than the one in memory pays a load.
- **Manual unload.** `DELETE /v1/ps/{engine}` unloads one engine (404 if it is unknown or not loaded); `POST /v1/unload` unloads all and returns the list. `GET /v1/ps` shows what is loaded.

Engines without weights never report `loaded: true`.

## Registry format

A registry is a JSON object with an `engines` map from slug to entry. `src/audiolla/config.py` loads it at startup and refuses to start when the file is missing, the map is empty, an entry is not an object or an `executor` is not one it knows. `AUDIOLLA_ENABLED_ENGINES` then filters it, and an unknown slug there also stops startup.

```json
{
  "engines": {
    "htdemucs": {
      "executor": "demucs",
      "variant": "htdemucs",
      "stems": ["drums", "bass", "other", "vocals"],
      "prefetch": "demucs"
    }
  }
}
```

| Field | Used by | Meaning |
| --- | --- | --- |
| `executor` | all | Backend class. One of `demucs`, `matchering`, `pedalboard_chain`, `librosa_analyze`, `sox_transform`, `fx_chain`, `midi_compose`, `midi_render`, `silence_detect`, `ffmpeg_render`, `audio_fingerprint`, `uvr_separator`, `basic_pitch`, `deepfilter`, `chord_detect`, `vad`, `diarize_pyannote`, `stretch`, `ast_tag`, `clap_embed`, `hpss`, `noise_reduce`, `metadata`, `stable_audio_open`, `musicgen`, `riffusion`, `audioldm2`. |
| `description` | all | Free text shown by `GET /v1/engines`. |
| `variant` | `demucs` | Demucs model name to load. |
| `stems` | separation engines | Stem names the engine can return. |
| `prefetch` | `demucs` | `"demucs"` makes `entrypoint.sh` download the checkpoint at startup. |
| `cuda_only` | any | `/v1/audio/separate` rejects the engine with 400 unless the server runs on a CUDA device. |
| `presets` | `pedalboard_chain` | Chain preset names. |
| `model`, `model_aggressive`, `primary_stem` | `uvr_separator` | Model file, optional aggressive model, and the stem returned as the result. |
| `hf_model` | `ast_tag`, `clap_embed` | Hugging Face model id. |
| `model_size` | `musicgen` | `small` or `medium`. |
| `license`, `noncommercial` | generators | License label; `noncommercial: true` entries need `AUDIOLLA_ENABLE_NONCOMMERCIAL=1`. |

To run a custom registry, mount it and point `AUDIOLLA_ENGINES_FILE` at it. Only the listed executors exist; a registry cannot add a new backend.

## Not included

| Left out | Why |
| --- | --- |
| MAGNeT, JASCO | CC-BY-NC weights from the same family as MusicGen, which already covers that ground behind the opt-in. |
| YuE 7B | Needs 16 to 24 GB of VRAM at fp16. |
| Essentia | AGPL v3: a network service using it has to publish its full source. librosa covers the common analysis. |
| Streaming separation | Demucs needs the whole file. There is no chunked or real-time inference. |
| VST3 plugin hosting | pedalboard can host plugins, but that needs your plugin directory mounted. Out of scope for the default image. |
| rubberband | GPL v2 or a commercial license. SoX and librosa cover pitch and tempo. |
