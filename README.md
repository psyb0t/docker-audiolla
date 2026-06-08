# audiolla

[![Docker Pulls](https://img.shields.io/docker/pulls/psyb0t/audiolla?style=flat-square)](https://hub.docker.com/r/psyb0t/audiolla)
[![Docker Hub](https://img.shields.io/docker/v/psyb0t/audiolla?sort=semver&label=Docker%20Hub&style=flat-square)](https://hub.docker.com/r/psyb0t/audiolla)
[![License: WTFPL](https://img.shields.io/badge/License-WTFPL-brightgreen.svg?style=flat-square)](http://www.wtfpl.net/)
[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg?style=flat-square)](https://www.python.org/downloads/)

**Thirty audio engines. One port. Zero cloud. Fire-and-forget async jobs. Webhooks.**

You needed Demucs for stems. Then librosa for BPM and key. Then basic-pitch for MIDI transcription. Then pyannote for speaker diarization. Then DeepFilterNet for speech enhancement. Then you spent three days debugging Python version conflicts and now you hate everything.

audiolla is what happens when you stop doing that.

Every audio processing tool worth using — wrapped in one HTTP API, running in one Docker container. POST a file. Get audio, JSON, or MIDI back. Drive it from curl, shell scripts, Python notebooks, Makefiles, or point an LLM agent at the MCP endpoint and let it rip.

No account. No subscription. No per-minute billing. No vendor lock-in. `docker run` and you're done.

---

## What's in the box

| | |
|--|--|
| 🎛️ **Stem separation** | Demucs — htdemucs, fine-tuned, 6-stem, MDX variants |
| 🎚️ **Mastering** | Reference mastering (matchering) + custom pedalboard chains |
| 📊 **Analysis** | BPM · key · LUFS · beats · onsets · melody · structural segments |
| 🎹 **Chords + key** | Chord detection + Krumhansl-Schmuckler key estimation |
| 🎵 **Audio → MIDI** | Polyphonic transcription via Spotify's basic-pitch (ONNX, no TF) |
| 🧹 **Restoration** | De-reverb · de-echo · de-noise via UVR BS-Roformer + MelBand Roformer |
| 🗣️ **Speech** | Enhancement (DeepFilterNet) · VAD (silero-vad) · diarization (pyannote) |
| 🖼️ **Visuals** | Spectrogram + waveform PNGs + 8-mode animated MP4/WebM |
| 🔍 **Fingerprint** | Chromaprint acoustic fingerprinting (AcoustID-compatible) |
| ✂️ **Silence** | Detect gaps · trim edges · strip all silence |
| 🎼 **MIDI pipeline** | Compose from JSON · inspect · transform · render via fluidsynth |
| 🎸 **Effects** | 23-effect pedalboard chain — Compressor, Reverb, PitchShift, filters… |
| 🔧 **Transforms** | Sox DSP — pitch, tempo, EQ, reverb, gain |
| 📢 **Loudness** | Measure LUFS · normalize to target |
| 🥁 **HPSS** | Harmonic/percussive source separation via librosa median filter |
| 🔇 **Noise reduction** | Spectral noise reduction via noisereduce — stationary + adaptive modes |
| ⏩ **Time-stretch** | Independent tempo factor + pitch shift via librosa phase vocoder |
| 🏷️ **Audio tagging** | Top-K AudioSet class labels via Audio Spectrogram Transformer |
| 🔗 **Audio embeddings** | 512-dim semantic embeddings via LAION CLAP + optional text similarity |
| 🏷️ **Zero-shot classify** | CLAP cosine similarity against any free-form text labels — genres, moods, instruments |
| 📋 **Audio info** | ffprobe metadata — duration, sample rate, channels, codec, bit depth |
| ✂️ **Trim** | Cut a clip by start/end seconds — any format in, any format out |
| 🎚️ **Mix** | Combine N staged tracks with per-track gain_db — pure ffmpeg, no model |
| 🔗 **Concat** | Stitch N audio files end-to-end in order |
| ⏩ **Speed** | Change playback speed without pitch shift (0.1× – 10×) via ffmpeg atempo |
| 🔄 **Convert** | Re-encode: format, sample rate, channel count in one call |
| 🔍 **Similar** | Cosine similarity between two audio files via CLAP embeddings |
| 🎹 **MIDI quantize** | Snap MIDI note timings to a rhythmic grid (16th, 8th, quarter…) |
| 🌅 **Fade** | Fade-in and/or fade-out with 13 curve shapes |
| ⏪ **Reverse** | Flip audio backwards |
| 🔁 **Loop** | Repeat audio N times |
| 🎯 **BPM match** | Auto-detect BPM then stretch to a target — no manual math |
| 📈 **Loudness curve** | RMS envelope over time — time-stamped dB values for gain automation |
| 🎤 **Pitch correct** | Auto-tune toward nearest chromatic semitone — configurable strength |
| 🔧 **Repair** | Declip + dehum — fix clipped peaks and remove power-line hum |
| 🔁 **Loop point** | Find best seamless loop boundary — score, bar count, candidates list |
| 🥁 **Drum machine** | Step-sequencer spec → GM drum MIDI — 16-step pattern, swing, tempo |
| 🎼 **Chords to MIDI** | Chord progression → MIDI file — root+3rd+5th voicings per segment |
| ↔️ **Stereo width** | Widen or collapse the stereo image via M/S processing |
| ✂️ **Split** | Split into N equal parts or on silence — returns ZIP of segments |
| 🔊 **Pan** | Position audio in the stereo field (-1 left → 0 center → 1 right) |
| 🎚️ **EQ** | Parametric EQ — JSON array of freq/gain_db/width_hz bands |
| 🎵 **Key match** | Detect source key then pitch-shift to a target key |
| 🎙️ **Sidechain duck** | Duck music when a trigger track (voice) is loud |
| 🏷️ **Metadata** | Read and write ID3/Vorbis/FLAC/WAV audio tags via mutagen |
| 🔴 **Clip detect** | Detect digital clipping — count, ratio, peak dBFS |
| ↔️ **Mid/Side** | Encode L/R → Mid+Side or decode Mid+Side → L/R |
| ✂️ **Beat slice** | Slice audio at detected beat positions — returns ZIP of segments |
| 🏟️ **Conv reverb** | Convolution reverb via impulse response — wet_mix control |
| 🥁 **Transient shaper** | Attack/sustain dual-compressor — punch up drums, cut room tail |
| 🎚️ **Multiband compress** | N-band compressor with zero-phase LR4 crossovers — mastering-grade dynamics |
| 🎛️ **DJ prep** | One call: BPM + key + Camelot wheel position + integrated LUFS |
| 📦 **Batch** | Run trim/convert/fade/reverse/speed/eq on staged files in sequence |
| 🧩 **Presets + pipeline** | Curated YAML workflows (`master-for-spotify`, `podcast-cleanup`, …) + ad-hoc op chaining server-side |
| 🗂️ **Catalog** | `GET /v1/catalog` — machine-readable endpoint list grouped by category for discovery |
| ⚡ **Async jobs** | Every endpoint supports `async_job=true` — fire-and-forget + webhook callbacks |

---

## Table of Contents

- [Run it](#run-it)
- [Quick start](#quick-start)
- [What it can do](#what-it-can-do)
  - [Split stems](#split-stems)
  - [Master](#master)
  - [Analyze](#analyze)
  - [Beats, onsets, melody, segments](#beats-onsets-melody-segments)
  - [Silence detection and trimming](#silence-detection-and-trimming)
  - [Visualize (spectrogram, waveform, video)](#visualize-spectrogram-waveform-video)
  - [Acoustic fingerprint](#acoustic-fingerprint)
  - [De-reverb, de-echo, de-noise](#de-reverb-de-echo-de-noise)
  - [Audio-to-MIDI transcription](#audio-to-midi-transcription)
  - [Neural speech and vocal enhancement](#neural-speech-and-vocal-enhancement)
  - [Chord and key detection](#chord-and-key-detection)
  - [Voice activity detection](#voice-activity-detection)
  - [Speaker diarization](#speaker-diarization)
  - [Transform](#transform)
  - [Loudness measurement](#loudness-measurement)
  - [Loudness curve](#loudness-curve)
  - [Loudness normalization](#loudness-normalization)
  - [HPSS (harmonic/percussive split)](#hpss-harmonicpercussive-split)
  - [Spectral noise reduction](#spectral-noise-reduction)
  - [Time-stretch and pitch-shift](#time-stretch-and-pitch-shift)
  - [Pitch correct](#pitch-correct)
  - [Repair](#repair)
  - [Audio tagging](#audio-tagging)
  - [Audio embeddings](#audio-embeddings)
  - [Zero-shot classification](#zero-shot-classification)
  - [Audio info](#audio-info)
  - [Trim](#trim)
  - [Mix](#mix)
  - [Concat](#concat)
  - [Speed](#speed)
  - [Convert](#convert)
  - [Similar](#similar)
  - [MIDI quantize](#midi-quantize)
  - [Fade](#fade)
  - [Reverse](#reverse)
  - [Loop](#loop)
  - [BPM match](#bpm-match)
  - [Stereo width](#stereo-width)
  - [Split](#split)
  - [Pan](#pan)
  - [EQ](#eq)
  - [Key match](#key-match)
  - [Sidechain duck](#sidechain-duck)
  - [Effects chain](#effects-chain)
  - [Loop point](#loop-point)
  - [Compose MIDI](#compose-midi)
  - [Inspect MIDI](#inspect-midi)
  - [Transform MIDI](#transform-midi)
  - [Render MIDI to audio](#render-midi-to-audio)
  - [Generate music from a spec](#generate-music-from-a-spec)
  - [Drum pattern](#drum-pattern)
  - [Chords to MIDI](#chords-to-midi)
  - [Audio metadata tags](#audio-metadata-tags)
  - [Clip detection](#clip-detection)
  - [Mid/Side encode and decode](#midside-encode-and-decode)
  - [Beat slice](#beat-slice)
  - [Convolution reverb](#convolution-reverb)
  - [Transient shaper](#transient-shaper)
  - [Multiband compression](#multiband-compression)
  - [DJ prep](#dj-prep)
  - [De-ess](#de-ess)
  - [Stereo field analysis](#stereo-field-analysis)
  - [Audio thumbnail](#audio-thumbnail)
  - [MIDI humanize](#midi-humanize)
  - [Batch operations](#batch-operations)
  - [Async jobs and webhooks](#async-jobs-and-webhooks)
  - [Stage files](#stage-files)
  - [Remote URLs](#remote-urls)
- [Engines](#engines)
- [Workflows — presets + pipeline](#workflows--presets--pipeline)
- [API catalog](#api-catalog)
- [Endpoints](#endpoints)
- [MCP](#mcp)
- [Configuration](#configuration)
- [What's not in here](#whats-not-in-here)
- [Build & dev](#build--dev)
- [Supply chain](#supply-chain)
- [License](#license)

---

## Run it

```bash
# no GPU
docker run --rm -it \
  -v $HOME/.audiolla-data:/data \
  -p 8000:8000 \
  psyb0t/audiolla:latest

# GPU
docker run --rm -it --gpus all \
  -v $HOME/.audiolla-data:/data \
  -e AUDIOLLA_DEVICE=cuda \
  -p 8000:8000 \
  psyb0t/audiolla:latest-cuda
```

Demucs weights prefetch at container startup (for whichever variants are enabled) and cache in `/data/torch_cache/`. First boot downloads them; same `-v` mount next time and they're already there. Other engines (matchering, pedalboard, librosa, sox, fx, midi) have no weights — they're ready as soon as `/healthz` is green.

---

## Migration from v0.23.x → v1.0.0

**v1.0.0 is a breaking API release.** Every existing client breaks. The new shape:

- Every audio endpoint takes a **JSON body** (no more `multipart/form-data` except at `/v1/files`)
- Input is **`file_path`** (FILES_DIR-relative) xor **`file_url`** (server-side fetch). Pre-stage the file via `PUT /v1/files/{path}` first.
- Output requires **`output_path`** xor **`output_url`**. No more raw audio bytes in responses.
- Async path: `async_job=true` auto-stages to `jobs/{id}.{ext}` if neither output is given.
- MCP audio-producing tools dropped `audio_base64` (and `midi_base64` / `image_base64` / `video_base64`). Same `output_path` xor `output_url` requirement.
- `openapi.yaml` is now the contract — Pydantic models regenerate from it via `make generate`. Never hand-edit `src/audiolla/schema/_generated.py`.

```diff
- curl -X POST http://localhost:8000/v1/audio/normalize \
-     -F "file=@track.wav" -F "target_lufs=-14" -o normalized.wav

+ # 1) stage the file (multipart only lives here now)
+ curl -X PUT --data-binary @track.wav \
+     -H 'Content-Type: application/octet-stream' \
+     http://localhost:8000/v1/files/uploads/track.wav

+ # 2) process via JSON body — response is JSON, not bytes
+ curl -X POST http://localhost:8000/v1/audio/normalize \
+     -H 'Content-Type: application/json' \
+     -d '{"file_path":"uploads/track.wav","target_lufs":-14,"output_path":"out/normalized.wav"}'

+ # 3) retrieve the result
+ curl -o normalized.wav http://localhost:8000/v1/files/out/normalized.wav
```

Why? See the [v1.0.0 CHANGELOG entry](CHANGELOG.md) for the full rationale.

## Quick start

Once the container is up, this is a complete audio pipeline in six commands (every audio endpoint is JSON-body now; stage your input file at `/v1/files/...` first):

```bash
# stage your input file
curl -X PUT --data-binary @song.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/song.wav

# rip the vocals out of a track
curl -X POST http://localhost:8000/v1/audio/separate \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/song.wav","engine":"htdemucs","stems":["vocals"],"output_path":"out/vocals.wav"}'
# → {"path":"out/vocals.wav","size":...,"output_format":"wav"}
curl -o vocals.wav http://localhost:8000/v1/files/out/vocals.wav

# what key is it in? what are the chords?
curl -X POST http://localhost:8000/v1/audio/chords \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/song.wav"}'
# → {"key":"F# minor","key_confidence":0.91,"chords":[{"chord":"F#m","start_sec":0.0,...},...]}

# transcribe that vocal melody to MIDI
curl -X PUT --data-binary @out/vocals.wav -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/vocals.wav  # only if not already staged
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocals.wav","output_path":"out/melody.mid"}'

# render the MIDI back to audio through a SoundFont
curl -X POST http://localhost:8000/v1/midi/render \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"out/melody.mid","output_path":"out/rendered.wav"}'

# strip background noise from a voice recording
curl -X POST http://localhost:8000/v1/audio/noise-reduce/uvr-denoise \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/interview.wav","output_path":"out/clean.wav"}'

# who's speaking and when?
curl -X POST http://localhost:8000/v1/audio/diarize/pyannote \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/interview.wav"}'
# → {"num_speakers":2,"segments":[{"speaker":"SPEAKER_00","start_sec":0.5,"end_sec":8.2},...]}
```

Audio in. MIDI out. Chords detected. Speakers identified. De-noised. Re-synthesized. No Python environment to set up. No API keys. No account. Just HTTP.

---

## What it can do

Output defaults to `wav`. Add `"output_format":"mp3"` to the JSON body to get mp3 instead (`flac`, `opus`, `aac`, `pcm` also work).

Every audio endpoint takes an `application/json` body. The only place multipart still lives is `PUT /v1/files/{path}` (raw bytes for staging an input file).

**Input** — every audio endpoint requires exactly one of:

- `file_path` — path inside the `/v1/files` staging area (stage with `PUT /v1/files/{path}` first)
- `file_url` — remote URL the server fetches (disabled by default — see [Remote URLs](#remote-urls))

**Output** — audio-producing endpoints require exactly one of:

- `output_path` — server writes to `/v1/files/<path>`, returns JSON `{"path":..., "size":..., ...}`
- `output_url` — server PUTs to a presigned URL, returns JSON `{"url":..., "size":..., ...}`

Analysis-only endpoints (those that return JSON data, e.g. `/v1/audio/analyze`, `/v1/audio/loudness`, `/v1/audio/info`) don't need `output_path` / `output_url` — the response is the result.

### Split stems

```bash
# stage input
curl -X PUT --data-binary @track.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/track.wav

# vocals only
curl -X POST http://localhost:8000/v1/audio/separate \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","engine":"htdemucs","stems":["vocals"],"output_path":"out/vocals.wav"}'
curl -o vocals.wav http://localhost:8000/v1/files/out/vocals.wav

# all 4 stems as a ZIP
curl -X POST http://localhost:8000/v1/audio/separate \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","engine":"htdemucs","output_path":"out/stems.zip"}'
curl -o stems.zip http://localhost:8000/v1/files/out/stems.zip
```

### Master

```bash
# stage track + reference
curl -X PUT --data-binary @track.wav -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/track.wav
curl -X PUT --data-binary @ref.wav -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/ref.wav

# match EQ + loudness to a reference track
curl -X POST http://localhost:8000/v1/audio/master \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","mode":"reference","reference_path":"uploads/ref.wav","output_path":"out/mastered.wav"}'
curl -o mastered.wav http://localhost:8000/v1/files/out/mastered.wav

# run a built-in pedalboard chain (presets: transparent, loud)
curl -X POST http://localhost:8000/v1/audio/master \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","mode":"chain","preset":"loud","output_path":"out/mastered.wav"}'
curl -o mastered.wav http://localhost:8000/v1/files/out/mastered.wav
```

### Analyze

```bash
# returns JSON. features: bpm, key, loudness, duration,
# spectral_centroid, rms, zcr. Omit features to get them all.
curl -X POST http://localhost:8000/v1/audio/analyze \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","features":["bpm","key","loudness"]}'
```

### Beats, onsets, melody, segments

```bash
# beat grid — returns bpm + beat timestamps
curl -X POST http://localhost:8000/v1/audio/beats \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'

# onset timestamps — note attacks, transients
curl -X POST http://localhost:8000/v1/audio/onsets \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'

# dominant melody contour — pitch in Hz per frame
curl -X POST http://localhost:8000/v1/audio/melody \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'

# structural segmentation — labels recurring sections A, B, C...
curl -X POST http://localhost:8000/v1/audio/segments \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","num_segments":4}'
```

Beat detection also generates a click-track file when `click_track=true` (set `output_path` to receive it) — handy for aligning a mix to a grid. Pass `start_bpm=140` to seed the tracker when you already know the rough tempo (faster, more accurate). Melody can be exported as a single-track MIDI file via `as_midi=true` + `output_path`.

### Silence detection and trimming

```bash
# find silent gaps in a recording (no trim_mode → JSON only)
curl -X POST http://localhost:8000/v1/audio/silence \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","threshold_db":-30,"min_duration_sec":1.0}'

# trim all silence and stage the result
curl -X POST http://localhost:8000/v1/audio/silence \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","threshold_db":-30,"min_duration_sec":0.5,"trim_mode":"all","output_path":"out/trimmed.wav"}'
curl -o trimmed.wav http://localhost:8000/v1/files/out/trimmed.wav

# trim only leading/trailing silence
curl -X POST http://localhost:8000/v1/audio/silence \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","threshold_db":-40,"min_duration_sec":0.3,"trim_mode":"edges","output_path":"processed/trimmed.wav"}'
```

`trim_mode=edges` — chop leading + trailing silence only. `trim_mode=all` — remove every detected gap (compress a talk recording, tighten a loop). Without `trim_mode`, the response is JSON only: `silent_ranges`, `non_silent_ranges`, `duration` — and `output_path` / `output_url` is not required.

### Visualize (spectrogram, waveform, video)

Visual output splits into two sub-namespaces by output type:

```bash
# Static PNG spectrogram (color + scale params)
curl -X POST http://localhost:8000/v1/audio/visualize/image/spectrogram \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","width":1280,"height":720,"output_path":"out/spec.png"}'
curl -o spec.png http://localhost:8000/v1/files/out/spec.png

# Static PNG waveform (color param)
curl -X POST http://localhost:8000/v1/audio/visualize/image/waveform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","width":1280,"height":240,"output_path":"out/wave.png"}'
curl -o wave.png http://localhost:8000/v1/files/out/wave.png

# Animated MP4 spectrum analyser (fps + container params)
curl -X POST http://localhost:8000/v1/audio/visualize/video/spectrum \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","width":1280,"height":720,"fps":30,"container":"mp4","output_path":"out/viz.mp4"}'
curl -o viz.mp4 http://localhost:8000/v1/files/out/viz.mp4
```

**`/image/spectrogram`**: produces a PNG (staged via `output_path` or PUT to `output_url`). Params: `width`, `height`, `color` (default `intensity`), `scale` (`log`/`lin`).

**`/image/waveform`**: produces a PNG. Params: `width`, `height`, `color` (default `lime`).

**`/video/{mode}`**: `spectrum` (scrolling FFT), `waves` (oscilloscope), `cqt` (constant-Q transform), `freqs` (bar-graph analyzer), `volume` (VU meter), `vectorscope` (stereo X/Y scope), `phasemeter`, `histogram`. Params: `width`, `height`, `fps`, `container` (`mp4` default, `webm`).

### Acoustic fingerprint

```bash
# Chromaprint fingerprint — identifies a recording regardless of encoding
curl -X POST http://localhost:8000/v1/audio/fingerprint \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# → {"duration": 215.34, "fingerprint": "AQADtEqRRIuQ..."}

# include the raw integer array (for custom similarity scoring)
curl -X POST http://localhost:8000/v1/audio/fingerprint \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","return_raw":true}'
```

The base64 fingerprint string is compatible with the [AcoustID](https://acoustid.org) lookup service.

### De-reverb, de-echo, de-noise

AI audio restoration via UVR ecosystem models — BS-Roformer and MelBand Roformer. All three are unified under `POST /v1/audio/restore/{engine}`.

```bash
# Remove room reverb (BS-Roformer, SDR 19+)
curl -X POST http://localhost:8000/v1/audio/restore/uvr-dereverb \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","output_path":"out/dry.wav"}'

# Remove echo — normal mode
curl -X POST http://localhost:8000/v1/audio/restore/uvr-deecho \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","output_path":"out/noecho.wav"}'

# Remove echo — aggressive mode (same engine, harder suppression)
curl -X POST http://localhost:8000/v1/audio/restore/uvr-deecho \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","aggressive":true,"output_path":"out/noecho.wav"}'

# Remove broadband background noise — ML (MelBand Roformer, SDR 28)
curl -X POST http://localhost:8000/v1/audio/restore/uvr-denoise \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","output_path":"out/clean.wav"}'
```

All support `output_format`, `output_path`, `output_url`. For DSP-based noise reduction (no GPU) use `noise-reduce/noise-reduce`.

UVR engines also work through `/v1/audio/separate` — `uvr-vocal-bsr` (BS-Roformer, SDR 13) and `uvr-karaoke` return vocal + instrumental stems like Demucs but often with higher quality.

### Audio-to-MIDI transcription

Polyphonic audio-to-MIDI via Spotify's basic-pitch (ONNX backend, no TensorFlow). Play guitar, hum a melody, record a piano riff — get a MIDI file back with all the notes.

```bash
# Any audio → MIDI file (staged)
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/guitar_riff.wav","output_path":"out/riff.mid"}'
curl -o riff.mid http://localhost:8000/v1/files/out/riff.mid

# Tune the detection thresholds
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/piano.wav","onset_threshold":0.6,"frame_threshold":0.3,"minimum_note_length_ms":80,"output_path":"out/piano.mid"}'

# Write directly to a different staging path
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"recordings/bass.wav","output_path":"midi/bass_notes.mid"}'
# → {"path":"midi/bass_notes.mid","size":...,"engine":"basic-pitch","output_format":"mid"}
```

Optional params: `onset_threshold` (0–1, default 0.5), `frame_threshold` (0–1, default 0.3), `minimum_note_length_ms` (default 58), `minimum_frequency` / `maximum_frequency` (Hz, default unconstrained), `multiple_pitch_bends` (bool, default false), `melodia_trick` (bool, default true — helps with melodic content). Default engine: `basic-pitch`.

The MIDI file is piped straight into `/v1/midi/inspect` or `/v1/midi/render` — audio → MIDI → audio is a complete round-trip.

### Neural speech and vocal enhancement

DeepFilterNet DF3 — deep learning noise suppression trained on speech. Better than broadband de-noise for voice recordings; more surgical than UVR's de-noise on vocals specifically.

```bash
# Enhance a vocal recording
curl -X POST http://localhost:8000/v1/audio/enhance/deepfilter \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal_recording.wav","output_path":"out/enhanced.wav"}'
curl -o enhanced.wav http://localhost:8000/v1/files/out/enhanced.wav

# Stage the output as mp3
curl -X POST http://localhost:8000/v1/audio/enhance/deepfilter \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"vocals/raw.wav","output_format":"mp3","output_path":"vocals/enhanced.mp3"}'
```

Supports `output_format`, `output_path`, `output_url`.

### Generate music + SFX

Text-to-audio generation under `POST /v1/audio/generate/{engine}`. v1.0.0 ships **five engines** spanning music + sound effects, with different licence / VRAM / sound profiles — all CUDA-only.

```bash
# Stable Audio Open 1.0 — 47s cap, no vocals, great for loops + SFX
curl -X POST http://localhost:8000/v1/audio/generate/stable-audio-open \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"130 bpm tech house drum loop, punchy kick, crisp hats, no vocals","duration_sec":10,"seed":42,"output_path":"out/loop.wav"}'
curl -o loop.wav http://localhost:8000/v1/files/out/loop.wav

# MusicGen 300M — 30s cap, instrumental, CC-BY-NC (opt-in required)
curl -X POST http://localhost:8000/v1/audio/generate/musicgen-small \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"lo-fi hip-hop beat with vinyl crackle, 90 bpm","duration_sec":15,"output_path":"out/beat.wav"}'

# Riffusion — spectrogram-to-audio via Griffin-Lim, ~5s, lo-fi character
curl -X POST http://localhost:8000/v1/audio/generate/riffusion \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"ambient drone with metallic resonance","output_path":"out/drone.wav"}'

# AudioLDM 2 — general SFX (no opt-in gate, CC-BY 4.0 commercial-OK)
curl -X POST http://localhost:8000/v1/audio/generate/audioldm2 \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"heavy rain on a metal roof with distant thunder","duration_sec":10,"num_inference_steps":50,"output_path":"out/rain.wav"}'
```

**Engine details:**

| Engine | Licence | Max length | VRAM (fp16) | Output |
|---|---|---|---|---|
| `stable-audio-open` | **Stability Community Licence** (commercial OK below the revenue threshold) | 47 s hard cap | ~12 GB | 44.1 kHz stereo. Loops, SFX, ambient textures — instrumental only |
| `musicgen-small` | **CC-BY-NC 4.0** (non-commercial only — opt-in via `AUDIOLLA_ENABLE_NONCOMMERCIAL=1`) | 30 s hard cap | ~3 GB | 32 kHz mono. Meta MusicGen 300M, instrumental |
| `musicgen-medium` | **CC-BY-NC 4.0** (same opt-in) | 30 s hard cap | ~6-8 GB | 32 kHz mono. Higher quality than -small |
| `riffusion` | **CreativeML OpenRAIL-M** (commercial OK with the licence's usage restrictions) | ~5 s per pass | ~3 GB | 22.05 kHz mono. SD-style spectrogram, Griffin-Lim reconstruction — lo-fi / loop-y character |
| `audioldm2` | **CC-BY 4.0** (commercial use OK — no opt-in gate) | 30 s hard cap | ~8-10 GB (CPU offload) | 16 kHz mono. General SFX: ambience, foley, animal, mechanical, impact sounds. Slow (200-step DDIM default; pass `num_inference_steps=50` for ~4x speedup) |

All engines support `async_job=true`, `webhook_url`, `output_path`, `output_url`, and `seed` for reproducibility. `stable-audio-open` and `audioldm2` additionally accept `num_inference_steps` (trade quality for speed). Model weights download on first call to `HF_HOME` (default `/data/hf` inside the container — ~7 GB across all five). Subsequent calls are inference-only. All five are flagged `cuda_only` — non-CUDA hosts get HTTP 400.

**Licence opt-in for MusicGen.** MusicGen weights are CC-BY-NC 4.0. The engine code ships with the image but refuses to load the model unless the operator explicitly sets `AUDIOLLA_ENABLE_NONCOMMERCIAL=1` in the server's environment. Same pattern matchering (GPL v3) follows — licence-encumbered code in the image, conscious opt-in to actually use it. Read [the MusicGen weights licence](https://github.com/facebookresearch/audiocraft/blob/main/LICENSE_weights) before opting in. **AudioLDM 2 is CC-BY 4.0** (commercial use allowed, no opt-in gate) — it's the only generator in this set that's commercial-safe without flipping any flags.

**Deferred to a future release** (researched but not shipped in v1.0.0):

- **ACE-Step v1** (3.5B, Apache 2.0, full songs with vocals up to 4 min) — requires `AceStepPipeline` from `diffusers>=0.38`, which itself requires a pre-release `safetensors`. Doesn't pass the project's hash-locked supply-chain gate. Revisit when `safetensors 0.8.x` ships stable, or vendor ACE-Step's pipeline directly.
- **DiffRhythm full v1.2** (Apache 2.0) — unpackaged research repo (no `setup.py` / PyPI release). Revisit when upstream ships a package or we vendor under `thirdparty/`.
- **Stable Audio Open Small** (Stability Community Licence, 11 s SFX-specialist) — requires `stable-audio-tools` which pins `python >=3.10, <3.11`; audiolla is on Python 3.12, hard incompatibility. Revisit when `stable-audio-tools` widens the Python constraint or diffusers grows a pipeline for it.
- **TangoFlux** (ICLR 2026, 44.1 kHz, 30 s, fast) — git-only install (no PyPI package). Could be SHA-pinned in the hash-locked supply chain; deferred for now to keep the heavy-deps stack PyPI-only.
- **AudioGen** (Meta, CC-BY-NC) — `audiocraft==1.3.0` pins `transformers<=4.31.0`, hard conflict with audiolla's 4.51.3. Would require an isolated subprocess / sidecar container.
- **YuE 7B** (Apache 2.0, full songs with vocals) — needs 16-24 GB VRAM at fp16, doesn't fit 12 GB GPUs without int4 quant tooling.

### Chord and key detection

Krumhansl-Schmuckler key estimation + chroma-template chord segmentation via librosa. No extra deps beyond the librosa stack.

```bash
curl -X POST http://localhost:8000/v1/audio/chords \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# → {
#     "key": "C major",
#     "key_confidence": 0.87,
#     "duration": 183.4,
#     "chords": [
#       {"chord": "C", "start_sec": 0.0, "end_sec": 2.3, "confidence": 0.91},
#       {"chord": "Am", "start_sec": 2.3, "end_sec": 4.6, "confidence": 0.85},
#       ...
#     ]
#   }

# Tune the hop length (lower = finer time resolution)
curl -X POST http://localhost:8000/v1/audio/chords \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","hop_length":256}'
```

Optional params: `hop_length` (default 512), `segment_min_duration_sec` (default 0.5 — merge very short chord segments).

### Voice activity detection

silero-vad — ONNX-based VAD, fast and accurate on both speech and music. Returns timestamped speech and non-speech segments.

```bash
curl -X POST http://localhost:8000/v1/audio/vad \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/interview.wav"}'
# → {
#     "speech_ratio": 0.73,
#     "duration": 120.0,
#     "threshold": 0.5,
#     "speech_segments": [
#       {"start_sec": 1.2, "end_sec": 8.4},
#       ...
#     ],
#     "non_speech_segments": [
#       {"start_sec": 0.0, "end_sec": 1.2},
#       ...
#     ]
#   }

# Tighter detection
curl -X POST http://localhost:8000/v1/audio/vad \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/podcast.wav","threshold":0.7,"min_speech_duration_ms":300,"min_silence_duration_ms":200}'
```

Optional params: `threshold` (0–1, default 0.5), `min_speech_duration_ms` (default 250), `min_silence_duration_ms` (default 100).

### Speaker diarization

pyannote/speaker-diarization-3.1 — state-of-the-art speaker diarization from HuggingFace Hub. Returns per-speaker timestamped segments and speaker count.

> **Note:** This engine requires a HuggingFace account. You must accept the model terms at
> [https://huggingface.co/pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1)
> and then set `HUGGINGFACE_TOKEN` when starting the container. A read-only token with model access is enough.

```bash
docker run ... \
  -e HUGGINGFACE_TOKEN=hf_your_token_here \
  psyb0t/audiolla:latest
```

```bash
curl -X POST http://localhost:8000/v1/audio/diarize/pyannote \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/interview.wav"}'
# → {
#     "num_speakers": 2,
#     "speakers": ["SPEAKER_00", "SPEAKER_01"],
#     "duration": 120.0,
#     "segments": [
#       {"speaker": "SPEAKER_00", "start_sec": 0.5, "end_sec": 8.2, "duration_sec": 7.7},
#       {"speaker": "SPEAKER_01", "start_sec": 8.5, "end_sec": 14.1, "duration_sec": 5.6},
#       ...
#     ]
#   }

# Hint the expected speaker count
curl -X POST http://localhost:8000/v1/audio/diarize/pyannote \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/roundtable.wav","num_speakers":4}'

# Or constrain the range
curl -X POST http://localhost:8000/v1/audio/diarize/pyannote \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/panel.wav","min_speakers":2,"max_speakers":6}'
```

Optional params: `num_speakers` (exact count hint), `min_speakers`, `max_speakers`.

### Transform

```bash
# pitch shift up 2 semitones + add reverb, export mp3.
# operations is a JSON array — ops: gain, equalizer, compand, reverb,
# pitch, tempo, rate, channels, trim, pad.
curl -X POST http://localhost:8000/v1/audio/transform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","operations":[{"op":"pitch","params":{"n_semitones":2}},{"op":"reverb","params":{"reverberance":50}}],"output_format":"mp3","output_path":"out/out.mp3"}'
curl -o out.mp3 http://localhost:8000/v1/files/out/out.mp3
```

### Loudness measurement

```bash
# Measure integrated LUFS — returns JSON, no audio output
curl -X POST http://localhost:8000/v1/audio/loudness \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# → {"loudness_lufs": -18.4}
```

### Loudness curve

RMS envelope over time — returns a list of `{time_sec, rms_db}` points. Useful for generating gain automation curves, finding loud and quiet sections, or visualising dynamic range before mastering.

```bash
# Default hop (512 samples) — fine-grained envelope
curl -X POST http://localhost:8000/v1/audio/loudness/curve \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}' | jq '.curve[:5]'
# → [
#     {"time_sec": 0.0,   "rms_db": -18.4},
#     {"time_sec": 0.012, "rms_db": -17.9},
#     ...
#   ]

# Coarser envelope (2048-sample hop)
curl -X POST http://localhost:8000/v1/audio/loudness/curve \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","hop_length":2048}' | jq '{duration, sample_rate, points}'
```

Response fields: `curve` (array of `{time_sec, rms_db}`), `duration` (seconds), `sample_rate`, `points` (total curve length). Optional param: `hop_length` (default 512).

### Loudness normalization

```bash
# Normalize to -14 LUFS (streaming platform standard)
curl -X POST http://localhost:8000/v1/audio/normalize \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","target_lufs":-14,"output_path":"out/normalized.wav"}'
curl -o normalized.wav http://localhost:8000/v1/files/out/normalized.wav

# Write to a different staging path
curl -X POST http://localhost:8000/v1/audio/normalize \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","target_lufs":-23,"output_path":"mastered/norm.wav"}'
```

`target_lufs` is required. The response JSON carries `loudness_lufs` with the measured pre-normalization level alongside `path` / `url` / `size`.

### HPSS (harmonic/percussive split)

Median-filter harmonic/percussive source separation via librosa. Harmonic = tonal content (pitched instruments, pads); percussive = transients (drums, percussion). No ML — pure DSP, fast, no GPU needed.

```bash
# Get both stems in a ZIP
curl -X POST http://localhost:8000/v1/audio/separate/hpss \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","output_path":"out/stems.zip"}'
curl -o stems.zip http://localhost:8000/v1/files/out/stems.zip
# → stems.zip contains harmonic.wav + percussive.wav

# Wider margin = harder separation (more aggressive)
curl -X POST http://localhost:8000/v1/audio/separate/hpss \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","margin":3.0,"output_path":"out/stems.zip"}'

# Output to a different staging path
curl -X POST http://localhost:8000/v1/audio/separate/hpss \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","output_path":"hpss/stems.zip"}'
```

Params: `margin` (default 1.0 — ≥1.0, higher = more aggressive), `kernel_size` (default 31 — odd int, median filter width), `output_format` (default `wav`).

### Spectral noise reduction

Noise reduction with two engine options under the same endpoint — pick DSP for no-GPU fast cleanup or ML for higher-quality removal.

```bash
# DSP (noisereduce) — no GPU, pure spectral subtraction + Wiener filtering
curl -X POST http://localhost:8000/v1/audio/noise-reduce/noise-reduce \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav","output_path":"out/clean.wav"}'

# Stationary mode — constant hum, hiss, fan noise
curl -X POST http://localhost:8000/v1/audio/noise-reduce/noise-reduce \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav","stationary":true,"output_path":"out/clean.wav"}'

# Partial reduction — subtle noise floor cleanup
curl -X POST http://localhost:8000/v1/audio/noise-reduce/noise-reduce \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav","prop_decrease":0.5,"output_path":"out/clean.wav"}'

# ML (UVR MelBand Roformer, SDR 28) — higher quality, GPU-accelerated
curl -X POST http://localhost:8000/v1/audio/noise-reduce/uvr-denoise \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav","output_path":"out/clean.wav"}'
```

DSP params (only apply to `noise-reduce` engine): `stationary` (bool, default `false`), `prop_decrease` (0–1, default 1.0). Both engines accept `output_format`, `output_path`, `output_url`.

### Time-stretch and pitch-shift

Independent tempo factor and semitone offset via librosa phase vocoder. Slow a track down to learn it; shift a vocal up 3 semitones for a different key; transpose a MIDI melody to a different register first, then render.

```bash
# Slow down to 80% speed, no pitch change
curl -X POST http://localhost:8000/v1/audio/stretch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","tempo_factor":0.8,"output_path":"out/slow.wav"}'

# Shift up 3 semitones, no tempo change
curl -X POST http://localhost:8000/v1/audio/stretch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal.wav","pitch_semitones":3,"output_path":"out/pitched.wav"}'

# Both — pitch-corrected time stretch (traditional chipmunk effect)
curl -X POST http://localhost:8000/v1/audio/stretch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","tempo_factor":0.5,"pitch_semitones":6,"output_format":"mp3","output_path":"out/stretched.mp3"}'
```

Params: `tempo_factor` (default 1.0 — 0.5 = half speed), `pitch_semitones` (default 0.0 — ±semitones), `output_format`, `output_path`.

### Pitch correct

Auto-tune audio toward the nearest chromatic semitone using librosa's phase vocoder. Full `strength=1.0` snaps hard to pitch; lower values blend the corrected and original signal.

```bash
# Hard auto-tune — snap every note to the nearest semitone
curl -X POST http://localhost:8000/v1/audio/pitch-correct \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal.wav","output_path":"out/tuned.wav"}'

# Subtle correction — 50% blend
curl -X POST http://localhost:8000/v1/audio/pitch-correct \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal.wav","strength":0.5,"output_format":"mp3","output_path":"out/tuned.mp3"}'

# Async for long files, staged output
curl -X POST http://localhost:8000/v1/audio/pitch-correct \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"sessions/take1.wav","strength":1.0,"async_job":true,"output_path":"sessions/take1_tuned.wav"}'
```

Params: `strength` (0.0–1.0, default 1.0), `output_format`, `output_path`, `async_job`, `webhook_url`. Requires `librosa-analyze` engine.

### Repair

Declip clipped peaks and/or remove power-line hum. Declipping uses cubic interpolation to reconstruct flattened waveform tops and bottoms. Dehumming applies a notch filter at `hum_freq` (and harmonics).

```bash
# Declip only (default)
curl -X POST http://localhost:8000/v1/audio/repair \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/overdriven.wav","output_path":"out/repaired.wav"}'

# Remove 60 Hz hum (North American power grid)
curl -X POST http://localhost:8000/v1/audio/repair \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav","declip":false,"dehum":true,"hum_freq":60.0,"output_path":"out/clean.wav"}'

# Both — declip a 50 Hz humming mic recording
curl -X POST http://localhost:8000/v1/audio/repair \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/problem_track.wav","declip":true,"dehum":true,"hum_freq":50.0,"output_format":"flac","output_path":"out/repaired.flac"}'
```

Params: `declip` (bool, default `true`), `dehum` (bool, default `false`), `hum_freq` (Hz, default 50.0), `output_format`, `output_path`, `async_job`, `webhook_url`.

### Audio tagging

Top-K AudioSet class label classification via Audio Spectrogram Transformer (MIT/ast-finetuned-audioset-10-10-0.4593). Identifies what's in a recording — music, speech, specific instruments, environmental sounds, etc.

```bash
curl -X POST http://localhost:8000/v1/audio/tag \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav"}'
# → {
#     "tags": [
#       {"label": "Music", "score": 0.94},
#       {"label": "Drum", "score": 0.87},
#       {"label": "Guitar", "score": 0.71},
#       ...
#     ],
#     "duration": 5.2
#   }

# Get top 20 results instead of the default 10
curl -X POST http://localhost:8000/v1/audio/tag \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/soundscape.wav","top_k":20}'
```

Requires the HF model cache. First run downloads the weights to `/data/hf/`. Optional: `top_k` (default 10).

> The image defaults to `HF_HUB_OFFLINE=0` so first call lazy-downloads the weights into `/data/hf/`. For locked-down deployments (no egress), prefetch the model with `huggingface-cli download <model>` into a mounted `/data/hf` volume, then start the container with `-e HF_HUB_OFFLINE=1`.

### Audio embeddings

512-dimensional L2-normalized audio embeddings via LAION CLAP (laion/larger_clap_music_and_speech). Useful for semantic audio search, similarity scoring, and clustering.

```bash
# Get the embedding vector
curl -X POST http://localhost:8000/v1/audio/embed \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# → {"embedding": [0.032, -0.11, ...], "dim": 512, "norm": 1.0}

# Semantic similarity — how well does the audio match a text description?
curl -X POST http://localhost:8000/v1/audio/embed \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","query_text":"energetic rock guitar riff"}'
# → {"embedding": [...], "dim": 512, "norm": 1.0,
#    "query_text": "energetic rock guitar riff", "similarity": 0.73}
```

`similarity` is cosine similarity in [-1, 1]. Requires HF model cache — same first-run download caveat as audio tagging.

### Zero-shot classification

Given audio and a list of free-form text labels, return cosine similarity scores for each using the existing CLAP model. No extra model download — uses the same `clap-embed` engine. Works for genres, moods, instruments, sonic descriptors — anything CLAP understands.

```bash
# Genre detection
curl -X POST http://localhost:8000/v1/audio/classify \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","labels":["jazz","hip-hop","classical","electronic","rock"]}'
# → {"results": [
#     {"label": "hip-hop", "score": 0.42},
#     {"label": "electronic", "score": 0.38},
#     ...
#   ]}

# Mood / energy
curl -X POST http://localhost:8000/v1/audio/classify \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","labels":["energetic","calm","melancholic","aggressive","uplifting"]}'

# Speaker gender
curl -X POST http://localhost:8000/v1/audio/classify \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/interview.wav","labels":["male voice","female voice","child voice","multiple speakers"]}'
```

Results are sorted by descending score. Scores are cosine similarities in [-1, 1] — higher = more similar. Requires `clap-embed` model cache.

### Audio info

Probe any audio file for metadata without loading it into memory for processing. Uses ffprobe — handles any format.

```bash
curl -X POST http://localhost:8000/v1/audio/info \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# → {
#     "size_bytes": 52428800,
#     "duration_sec": 297.241,
#     "sample_rate": 44100,
#     "channels": 2,
#     "codec": "pcm_s16le",
#     "sample_fmt": "s16",
#     "format": "wav",
#     "bit_depth": 16,
#     "bit_rate": 1411200
#   }

# Works on any staged file
curl -X POST http://localhost:8000/v1/audio/info \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"recordings/interview.mp3"}'
# → {"codec": "mp3", "bit_rate": 192000, ...}
```

### Trim

Cut a precise time range out of any audio file. Common use: extract a chorus, clip a sample, chop a stem at bar boundaries.

```bash
# Extract seconds 30–90 from a track
curl -X POST http://localhost:8000/v1/audio/trim \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","start_sec":30.0,"end_sec":90.0,"output_path":"out/chorus.wav"}'

# Clip a specific beat range, export as mp3
curl -X POST http://localhost:8000/v1/audio/trim \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/stem.wav","start_sec":0.0,"end_sec":8.0,"output_format":"mp3","output_path":"out/loop.mp3"}'

# From staged file, write to a different staging path
curl -X POST http://localhost:8000/v1/audio/trim \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"sessions/full.wav","start_sec":120.5,"end_sec":180.0,"output_path":"clips/verse.wav"}'
```

`start_sec` defaults to 0. `end_sec` is required and must be greater than `start_sec`. Supports all standard `output_format` values.

### Mix

Combine multiple staged or URL-accessible tracks into one. Per-track `gain_db` lets you balance levels before mixing. Useful for bouncing separated stems back together at custom levels, layering synth parts, or combining click-track + music.

```bash
# Mix drums and bass at equal levels
curl -X POST http://localhost:8000/v1/audio/mix \
  -H 'Content-Type: application/json' \
  -d '{"tracks":[{"file_path":"stems/drums.wav"},{"file_path":"stems/bass.wav"}],"output_path":"out/rhythm.wav"}'

# Stems at custom levels (drums -3 dB, bass 0 dB, vocals +2 dB)
curl -X POST http://localhost:8000/v1/audio/mix \
  -H 'Content-Type: application/json' \
  -d '{"tracks":[
    {"file_path":"stems/drums.wav","gain_db":-3},
    {"file_path":"stems/bass.wav","gain_db":0},
    {"file_path":"stems/vocals.wav","gain_db":2}
  ],"output_format":"wav","output_path":"out/custom_mix.wav"}'

# Write to a different staging path
curl -X POST http://localhost:8000/v1/audio/mix \
  -H 'Content-Type: application/json' \
  -d '{"tracks":[{"file_path":"stems/harmonic.wav"},{"file_path":"stems/percussive.wav","gain_db":-6}],"output_path":"mixed/recombined.wav"}'
```

`tracks` is a required JSON array. Each entry needs `file_path` or `file_url` and an optional `gain_db` (default 0.0). Requires at least 2 tracks. Shorter tracks are padded with silence to match the longest.

### Concat

Stitch N audio files together in order. Handles different sample rates and channel counts automatically (ffmpeg resamples on the fly).

```bash
curl -X POST http://localhost:8000/v1/audio/concat \
  -H 'Content-Type: application/json' \
  -d '{"files":[{"file_path":"intro.wav"},{"file_path":"verse.wav"},{"file_path":"outro.wav"}],"output_path":"out/full_track.wav"}'

# output_format change + different staging path
curl -X POST http://localhost:8000/v1/audio/concat \
  -H 'Content-Type: application/json' \
  -d '{"files":[{"file_path":"a.wav"},{"file_path":"b.wav"}],"output_format":"mp3","output_path":"concat/result.mp3"}'
```

`files` is a required JSON array of `{file_path?, file_url?}` objects. Requires at least 2 entries.

### Speed

Change playback speed without pitch shifting — useful for auditioning at half/double speed, or creating slow-motion effects. Uses ffmpeg `atempo` filter chained for extreme multipliers.

```bash
# Half speed
curl -X POST http://localhost:8000/v1/audio/speed \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","speed":0.5,"output_path":"out/slow.wav"}'

# Double speed
curl -X POST http://localhost:8000/v1/audio/speed \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","speed":2.0,"output_path":"out/fast.wav"}'

# 4× speed (chains two atempo=2.0 filters internally)
curl -X POST http://localhost:8000/v1/audio/speed \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","speed":4.0,"output_format":"mp3","output_path":"out/fast.mp3"}'
```

`speed` is required. Range: 0.1–10.0. Note: this changes duration but not pitch. For pitch-preserving tempo changes use `/v1/audio/stretch`.

### Convert

Re-encode audio to a different format, sample rate, or channel count in a single call.

```bash
# WAV → 16 kHz mono FLAC (for speech models)
curl -X POST http://localhost:8000/v1/audio/convert \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav","output_format":"flac","sample_rate":16000,"channels":1,"output_path":"out/prepared.flac"}'

# Stereo → mono WAV
curl -X POST http://localhost:8000/v1/audio/convert \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stereo.wav","channels":1,"output_path":"out/mono.wav"}'

# Any format → Opus at 48 kHz
curl -X POST http://localhost:8000/v1/audio/convert \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/audio.mp3","output_format":"opus","sample_rate":48000,"output_path":"out/out.opus"}'
```

`output_format` defaults to `wav`. `sample_rate` and `channels` are optional; if omitted, the source values are preserved.

### Similar

Compute cosine similarity between two audio files using CLAP embeddings. Returns a score in [-1, 1] — 1 = identical sound, 0 = unrelated, negative = acoustically opposite. Useful for duplicate detection, cover matching, or finding the closest sample in a library.

```bash
curl -X POST http://localhost:8000/v1/audio/similar \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/original.wav","reference_file_path":"uploads/remix.wav"}'
# → {"similarity": 0.847, "dim": 512}

# Different staged paths
curl -X POST http://localhost:8000/v1/audio/similar \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stems/vocals.wav","reference_file_path":"stems/vocals_ref.wav"}'
```

Primary file: `file_path` / `file_url`. Reference file: `reference_file_path` / `reference_file_url`. Requires `clap-embed` engine.

### MIDI quantize

Snap all note timings in a MIDI file to the nearest rhythmic grid. Cleaner dedicated endpoint than `/v1/midi/transform`'s `quantize_grid_beats` param.

```bash
# Quantize to 16th notes (0.25 beats)
curl -X POST http://localhost:8000/v1/midi/quantize \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/sloppy.mid","grid_beats":0.25,"output_path":"out/tight.mid"}'

# 8th note grid
curl -X POST http://localhost:8000/v1/midi/quantize \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"recorded.mid","grid_beats":0.5,"output_path":"midi/quantized.mid"}'
```

`grid_beats`: grid size in beats — `0.25` = 16th note, `0.5` = 8th, `1.0` = quarter note. Default: `0.25`.

### Fade

Apply fade-in, fade-out, or both. 13 curve shapes: `tri`, `qsin`, `esin`, `hsin`, `log`, `ipar`, `qua`, `cub`, `squ`, `cbr`, `par`, `exp`, `lin`.

```bash
# 2s fade-in
curl -X POST http://localhost:8000/v1/audio/fade \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","fade_in":2.0,"output_path":"out/faded.wav"}'

# 3s fade-out with exponential curve
curl -X POST http://localhost:8000/v1/audio/fade \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","fade_out":3.0,"curve":"exp","output_path":"out/faded.wav"}'

# Both — 1s in, 2s out
curl -X POST http://localhost:8000/v1/audio/fade \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","fade_in":1.0,"fade_out":2.0,"output_path":"out/faded.wav"}'
```

At least one of `fade_in` / `fade_out` must be > 0.

### Reverse

Flip audio backwards via ffmpeg `areverse`.

```bash
curl -X POST http://localhost:8000/v1/audio/reverse \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/sample.wav","output_path":"out/reversed.wav"}'

curl -X POST http://localhost:8000/v1/audio/reverse \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stems/vocals.wav","output_format":"mp3","output_path":"out/reversed.mp3"}'
```

### Loop

Repeat audio N times. Uses ffmpeg `aloop` filter — no re-encoding overhead per iteration.

```bash
# Play 4 times total
curl -X POST http://localhost:8000/v1/audio/loop \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/beat.wav","count":4,"output_path":"out/looped.wav"}'

# 8-bar loop → 32 bars
curl -X POST http://localhost:8000/v1/audio/loop \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stems/drums.wav","count":4,"output_path":"loops/drums32.wav"}'
```

`count` must be ≥ 2 (total plays, not extra loops).

### BPM match

Detect the source BPM via librosa, then time-stretch to the target — no manual math.

```bash
# Stretch anything to 128 BPM
curl -X POST http://localhost:8000/v1/audio/bpm-match \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/loop.wav","target_bpm":128,"output_path":"out/matched.wav"}'

# Match tempo and also shift pitch
curl -X POST http://localhost:8000/v1/audio/bpm-match \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/loop.wav","target_bpm":140,"pitch_semitones":2,"output_path":"out/matched.wav"}'
```

Response JSON includes `source_bpm`, `target_bpm`, and `tempo_factor` alongside the staged `path` / `url`. Requires both `librosa-analyze` and `stretch` engines.

### Stereo width

Widen or collapse the stereo image via M/S processing. `width=0.0` → mono, `1.0` → original, `>1.0` → wider. Works on mono input too (upmixes first).

```bash
# Widen to 1.5×
curl -X POST http://localhost:8000/v1/audio/stereo-width \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/mix.wav","width":1.5,"output_path":"out/wide.wav"}'

# Collapse to mono
curl -X POST http://localhost:8000/v1/audio/stereo-width \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/mix.wav","width":0.0,"output_path":"out/mono.wav"}'

# Subtle narrowing for mix bus
curl -X POST http://localhost:8000/v1/audio/stereo-width \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"master/mix.wav","width":0.8,"output_path":"master/narrow.wav"}'
```

Range: `[0.0, 3.0]`.

### Split

Split a file into segments. Two modes: `equal` (N equal time parts) or `silence` (split on quiet gaps). Returns a ZIP of numbered files.

```bash
# Split into 4 equal parts
curl -X POST http://localhost:8000/v1/audio/split \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","mode":"equal","count":4,"output_path":"out/segments.zip"}'

# Split a DJ mix on silence
curl -X POST http://localhost:8000/v1/audio/split \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/djmix.wav","mode":"silence","threshold_db":-40,"min_duration_sec":1.0,"output_path":"out/tracks.zip"}'

# Split to mp3
curl -X POST http://localhost:8000/v1/audio/split \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/album.flac","mode":"equal","count":10,"output_format":"mp3","output_path":"out/parts.zip"}'
```

`mode=equal` requires `count >= 2`. `mode=silence` uses `threshold_db` (default -30) and `min_duration_sec` (default 0.5); requires the `silence-detect` engine.

### Pan

Position audio in the stereo field. Works on mono and stereo input.

```bash
# Hard left
curl -X POST http://localhost:8000/v1/audio/pan \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal.wav","position":-1.0,"output_path":"out/left.wav"}'

# Slight right (e.g. guitar in mix)
curl -X POST http://localhost:8000/v1/audio/pan \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stems/guitar.wav","position":0.4,"output_path":"out/guitar_panned.wav"}'

# Center (no-op but valid)
curl -X POST http://localhost:8000/v1/audio/pan \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/mono.wav","position":0.0,"output_path":"out/stereo.wav"}'
```

`position`: -1.0 = hard left, 0.0 = center, 1.0 = hard right.

### EQ

Parametric EQ via ffmpeg `equalizer` filter. Pass any number of bands — each with a center frequency, gain, and optional bandwidth.

```bash
# Low-cut + presence boost
curl -X POST http://localhost:8000/v1/audio/eq \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal.wav","bands":[{"freq":100,"gain_db":-6,"width_hz":80},{"freq":3000,"gain_db":3,"width_hz":500}],"output_path":"out/eq.wav"}'

# Single band: cut 60 Hz hum
curl -X POST http://localhost:8000/v1/audio/eq \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav","bands":[{"freq":60,"gain_db":-20,"width_hz":30}],"output_path":"out/clean.wav"}'
```

Each band: `freq` (Hz, required), `gain_db` (dB, required, range ±30), `width_hz` (optional, default 100).

### Key match

Detect the source key via CLAP chord analysis, then pitch-shift to a target key — one call instead of two.

```bash
# Shift everything to C major
curl -X POST http://localhost:8000/v1/audio/key-match \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/loop.wav","target_key":"C","output_path":"out/matched.wav"}'

# Match to F# (response includes source_key + semitones shifted)
curl -X POST http://localhost:8000/v1/audio/key-match \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stems/melody.wav","target_key":"F#","output_path":"matched/melody_fsharp.wav"}'
```

`target_key`: root note, e.g. `C`, `F#`, `Bb`, `D#`. Mode suffix (`major`/`minor`/`m`) is ignored — only the root matters for pitch. Requires `chord-detect` and `stretch` engines.

### Sidechain duck

Duck a primary track (music) whenever a trigger track (voice) is loud — the classic voiceover-over-music effect. Pure ffmpeg `sidechaincompress`, no model required.

```bash
# stage music + voice first via PUT /v1/files/...

curl -X POST http://localhost:8000/v1/audio/sidechain-duck \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/music.wav","trigger_file_path":"uploads/voice.wav","threshold_db":-20,"ratio":4,"attack_ms":10,"release_ms":200,"output_path":"out/ducked.wav"}'

# Aggressive duck for podcast-style music bed
curl -X POST http://localhost:8000/v1/audio/sidechain-duck \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"music/bed.wav","trigger_file_path":"voice/narration.wav","threshold_db":-30,"ratio":10,"release_ms":400,"output_path":"final/mix.wav"}'
```

Primary track is compressed whenever the trigger exceeds `threshold_db`. `ratio` sets compression intensity. Files must be the same duration for best results; shorter trigger is padded with silence.

### Effects chain

Apply an ordered chain of pedalboard effects — full catalog, you pick the order and params. Different from `/v1/audio/master` (which runs preset mastering chains).

```bash
# Compress, then add reverb, then drop -3 dB
curl -X POST http://localhost:8000/v1/audio/fx \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","effects":[
    {"type":"Compressor","params":{"threshold_db":-18,"ratio":4.0}},
    {"type":"Reverb","params":{"room_size":0.5,"wet_level":0.3}},
    {"type":"Gain","params":{"gain_db":-3.0}}
  ],"output_path":"out/out.wav"}'
```

Allowed effects: `Compressor`, `Limiter`, `NoiseGate`, `Gain`, `Clipping`, `Distortion`, `Bitcrush`, `Reverb`, `Chorus`, `Delay`, `Phaser`, `PitchShift`, `HighShelfFilter`, `LowShelfFilter`, `PeakFilter`, `HighpassFilter`, `LowpassFilter`, `LadderFilter`, `IIRFilter`, `GSMFullRateCompressor`, `MP3Compressor`, `Resample`, `Invert`, `Convolution`.

VST3 / AudioUnit / external plugins are NOT in the allowlist — they load arbitrary native code.

### Loop point

Find the best seamless loop boundary in an audio file — audiolla analyses the beat grid and returns the start and end positions where a loop will repeat without a click or gap.

```bash
# Find best loop boundary (default: minimum 4 bars)
curl -X POST http://localhost:8000/v1/audio/loop-point \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/beat.wav"}' | jq '{loop_start_sec, loop_end_sec, bars, score, tempo_bpm}'
# → {"loop_start_sec": 0.0, "loop_end_sec": 7.44, "bars": 4,
#    "score": 0.94, "tempo_bpm": 128.0, "candidates": [...]}

# Require at least 8 bars, return top 3 candidates
curl -X POST http://localhost:8000/v1/audio/loop-point \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/long_track.wav","min_loop_bars":8,"num_candidates":3}'
```

Response fields: `loop_start_sec`, `loop_end_sec`, `bars`, `score` (0–1, higher = tighter loop), `tempo_bpm`, `candidates` (array of ranked alternatives). Optional params: `min_loop_bars` (default 4), `num_candidates` (default 5). Requires `librosa-analyze` engine.

### Compose MIDI

POST a JSON song spec, get Standard MIDI File bytes back. Write the spec by hand, generate it from a tracker / DAW / sequencer, script it out of a Python notebook, or have an LLM produce it — audiolla doesn't care. No AI runs server-side; the spec is the music.

```bash
# 4-beat C major arpeggio at 120 BPM, piano + kick drum
curl -X POST http://localhost:8000/v1/midi/compose \
  -H 'Content-Type: application/json' \
  -d '{
    "tempo_bpm": 120,
    "tracks": [
      {"name":"Lead","program":0,"channel":0,"notes":[
        {"pitch":60,"start_beats":0.0,"duration_beats":0.5,"velocity":100},
        {"pitch":64,"start_beats":0.5,"duration_beats":0.5,"velocity":100},
        {"pitch":67,"start_beats":1.0,"duration_beats":0.5,"velocity":100},
        {"pitch":72,"start_beats":1.5,"duration_beats":0.5,"velocity":100}
      ]},
      {"name":"Kick","program":0,"channel":9,"notes":[
        {"pitch":36,"start_beats":0.0,"duration_beats":0.1,"velocity":110},
        {"pitch":36,"start_beats":1.0,"duration_beats":0.1,"velocity":110},
        {"pitch":36,"start_beats":2.0,"duration_beats":0.1,"velocity":110},
        {"pitch":36,"start_beats":3.0,"duration_beats":0.1,"velocity":110}
      ]}
    ],
    "output_path": "midi/song.mid"
  }'
curl -o song.mid http://localhost:8000/v1/files/midi/song.mid

# Use a JSON spec file (must include output_path / output_url in the body)
curl -X POST http://localhost:8000/v1/midi/compose \
  -H 'Content-Type: application/json' \
  -d @spec.json
```

Spec fields: `tempo_bpm` (default 120), `time_signature` (default `[4,4]`), `key_signature` (optional, e.g. `"C"`, `"Am"`), `ticks_per_beat` (default 480), `tracks[].{name, program, channel, volume, pan, notes[].{pitch, start_beats, duration_beats, velocity}}`. Time is in beats. `program` is GM program 0-127. Channel 9 is the GM drum channel — pitches there map to the drum kit (36 = kick, 38 = snare, 42 = closed hi-hat, etc.).

### Inspect MIDI

```bash
# read the structure of any Standard MIDI File
curl -X POST http://localhost:8000/v1/midi/inspect \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid"}'
# → {type, ticks_per_beat, tempo_changes, time_signatures,
#    tracks[{name, note_on_count, channels, programs, length_beats}], ...}
```

### Transform MIDI

```bash
# transpose all non-drum tracks up an octave
curl -X POST http://localhost:8000/v1/midi/transform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","transpose_semitones":12,"output_path":"midi/transposed.mid"}'

# override tempo to 140 BPM and save to staging
curl -X POST http://localhost:8000/v1/midi/transform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","tempo_bpm":140,"output_path":"midi/fast.mid"}'

# drop the drum track (channel 9)
curl -X POST http://localhost:8000/v1/midi/transform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","drop_channels":[9],"output_path":"midi/no-drums.mid"}'

# keep only channels 0 and 1
curl -X POST http://localhost:8000/v1/midi/transform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","keep_channels":[0,1],"output_path":"midi/two-ch.mid"}'

# quantize to 1/16th notes
curl -X POST http://localhost:8000/v1/midi/transform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","quantize_grid_beats":0.25,"output_path":"midi/quantized.mid"}'
```

`transpose_semitones` ±48. `quantize_grid_beats` is in beats (0.25 = 1/16th at 4/4). `keep_channels` and `drop_channels` take a JSON array of channel numbers; only one can be set per request.

### Render MIDI to audio

```bash
# Synthesise via the bundled FluidR3_GM SoundFont
curl -X POST http://localhost:8000/v1/midi/render \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","output_format":"wav","output_path":"out/song.wav"}'
curl -o song.wav http://localhost:8000/v1/files/out/song.wav

# Use your own SoundFont (must be staged first)
curl -X PUT --data-binary @my.sf2 \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/sf/orchestral.sf2
curl -X POST http://localhost:8000/v1/midi/render \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","soundfont_path":"sf/orchestral.sf2","output_format":"flac","output_path":"out/orch.flac"}'
```

### Generate music from a spec

Compose + render in one call — spec in, audio file staged.

```bash
# spec.json must include "output_path" or "output_url" alongside the composition fields
curl -X POST http://localhost:8000/v1/midi/generate \
  -H 'Content-Type: application/json' \
  -d @spec.json
curl -o song.wav http://localhost:8000/v1/files/out/song.wav
```

### Drum pattern

Step-sequencer spec → GM drum MIDI. Define a rhythmic pattern as arrays of 0/1 step values for each drum voice; the server maps them to GM channel 9 pitches and bakes a MIDI file. Optional swing shifts even-numbered 16th steps for a shuffled feel.

```bash
# 4-on-the-floor kick, snare on 2&4, busy hi-hat — 2 bars at 120 BPM
curl -X POST http://localhost:8000/v1/midi/drum \
  -H "Content-Type: application/json" \
  -d '{
    "tempo_bpm": 120,
    "steps": 16,
    "bars": 2,
    "swing": 0.0,
    "pattern": {
      "kick":  [1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0],
      "snare": [0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0],
      "hihat": [1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]
    },
    "output_path": "midi/beat.mid"
  }'
curl -o beat.mid http://localhost:8000/v1/files/midi/beat.mid

# Swing groove — 0.1 = subtle, 0.5 = strong shuffle
curl -X POST http://localhost:8000/v1/midi/drum \
  -H "Content-Type: application/json" \
  -d '{
    "tempo_bpm": 95,
    "steps": 16,
    "bars": 1,
    "swing": 0.2,
    "pattern": {
      "kick":  [1,0,0,1,0,0,1,0,1,0,0,1,0,0,1,0],
      "snare": [0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0],
      "hihat": [1,0,1,0,1,0,1,0,1,0,1,0,1,0,1,0]
    },
    "output_path": "midi/groove.mid"
  }'
```

Body fields: `tempo_bpm` (default 120), `steps` (steps per bar, default 16), `bars` (default 1), `swing` (0.0–0.5, default 0.0), `pattern` (object — keys are drum voice names, values are arrays of 0/1). Supported voices: `kick`, `snare`, `hihat`, `open_hihat`, `ride`, `crash`, `clap`, `tom_hi`, `tom_mid`, `tom_low`, `rim`, `cowbell`. Requires `midi-compose` engine.

### Chords to MIDI

Detect the chord progression from an audio file and convert each segment to a MIDI chord (root + 3rd + 5th). Useful for exporting a detected chord chart as playable MIDI, re-harmonising an arrangement, or seeding a DAW session.

```bash
# Audio → chord MIDI at the detected tempo
curl -X POST http://localhost:8000/v1/audio/chords-to-midi \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","output_path":"out/chords.mid"}'

# Override tempo, set velocity and octave
curl -X POST http://localhost:8000/v1/audio/chords-to-midi \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/song.wav","tempo_bpm":120,"velocity":90,"octave":3,"output_path":"out/chords.mid"}'

# Stage the output under a different path
curl -X POST http://localhost:8000/v1/audio/chords-to-midi \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"sessions/song.wav","output_path":"midi/song_chords.mid"}'
```

Optional params: `tempo_bpm` (default: detected from audio), `velocity` (1–127, default 80), `octave` (0–8, default 4), `output_path`. Requires `chord-detect` engine. Each chord segment becomes a MIDI chord event (root + major 3rd/minor 3rd + perfect 5th, duration = segment length).

### Audio metadata tags

Read and write ID3 (MP3), Vorbis (OGG/FLAC), and WAV/M4A tags via mutagen. Requires the `metadata` engine.

```bash
# Read tags
curl -X POST http://localhost:8000/v1/audio/metadata \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.mp3"}' | jq '{title, artist, bpm, key, duration_sec}'

# Write tags — returns updated tag set
curl -X POST http://localhost:8000/v1/audio/metadata \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.mp3","tags":{"title":"My Track","artist":"DJ Audiolla","bpm":"128","year":"2026"}}'
```

### Clip detection

Detect digital clipping. No engine required — pure numpy arithmetic.

```bash
curl -X POST http://localhost:8000/v1/audio/clip-detect \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/loud_master.wav"}' | jq '{clipped, clip_count, clip_ratio, peak_db}'
# → {"clipped":true,"clip_count":4219,"clip_ratio":0.0048,"peak_db":0.0}
```

### Mid/Side encode and decode

Encode L/R stereo to Mid+Side or decode back. Useful for stereo width surgery without touching the pedalboard chain.

```bash
# Encode L/R → M/S
curl -X POST http://localhost:8000/v1/audio/mid-side \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/stereo.wav","mode":"encode","output_path":"out/ms_encoded.wav"}'

# Decode back to L/R
curl -X POST http://localhost:8000/v1/audio/mid-side \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"out/ms_encoded.wav","mode":"decode","output_path":"out/restored.wav"}'
```

### Beat slice

Detect beat positions with librosa and return a ZIP of numbered WAV/MP3 slices — one file per beat interval.

```bash
curl -X POST http://localhost:8000/v1/audio/beat-slice \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/loop.wav","output_format":"wav","output_path":"out/slices.zip"}'
curl -o slices.zip http://localhost:8000/v1/files/out/slices.zip
# → slices.zip: beat_001.wav, beat_002.wav, beat_003.wav …

# Stage the ZIP at a different path
curl -X POST http://localhost:8000/v1/audio/beat-slice \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/loop.wav","output_path":"beats/loop_slices.zip"}'
# → {"path":"beats/loop_slices.zip","beat_count":32,...}
```

### Convolution reverb

Apply an impulse response (IR) to audio via pedalboard's `Convolution`. Any WAV file can be used as the IR.

```bash
# Upload your IR first
curl -X PUT --data-binary @plate_reverb.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/ir/plate.wav

# Apply — wet_mix: 0.0=dry only, 1.0=wet only
curl -X POST http://localhost:8000/v1/audio/conv-reverb \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/dry_vocal.wav","ir_file_path":"ir/plate.wav","wet_mix":0.25,"output_format":"wav","output_path":"out/reverbed.wav"}'
```

### Transient shaper

Attack/sustain dual-compressor blending. Positive `attack_gain_db` makes drums punchier; negative `sustain_gain_db` cuts room tail.

```bash
# Punchy drums: boost attack, cut sustain
curl -X POST http://localhost:8000/v1/audio/transient \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/drums.wav","attack_gain_db":6,"sustain_gain_db":-4,"output_path":"out/punchy_drums.wav"}'

# Soft attack (pad-like)
curl -X POST http://localhost:8000/v1/audio/transient \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/synth.wav","attack_gain_db":-6,"sustain_gain_db":0,"output_path":"out/softened.wav"}'
```

### Multiband compression

Split the signal into N+1 frequency bands and compress each one independently. Bands are split with zero-phase LR4-equivalent crossovers, so a bypassed chain reconstructs the original. Mastering-engineer staple — tame bass thump without squashing vocal sibilance, level out a busy mid-range, etc.

```bash
# 3-band mastering pass: low/mid/high
curl -X POST http://localhost:8000/v1/audio/multiband-compress \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/mixdown.wav","crossovers_hz":[200,3000],"bands":[
    {"threshold_db":-18,"ratio":4,"attack_ms":15,"release_ms":150,"makeup_db":1.5},
    {"threshold_db":-14,"ratio":3,"attack_ms":8, "release_ms":80, "makeup_db":1.0},
    {"threshold_db":-10,"ratio":2,"attack_ms":3, "release_ms":40, "makeup_db":0.5}
  ],"output_path":"out/mastered.wav"}'
```

`crossovers_hz` length is N, `bands` length is N+1. Each band: required `threshold_db` + `ratio`, optional `attack_ms` (default 10), `release_ms` (default 100), `makeup_db` (default 0).

### DJ prep

One call returns everything a DJ needs about a track. Requires `librosa-analyze` + `chord-detect`. LUFS is reported when a loudness engine is available.

```bash
curl -X POST http://localhost:8000/v1/audio/dj-prep \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}' | jq .
# → {"bpm":128.0,"key":"A minor","camelot":"8A","integrated_lufs":-9.4}
```

Camelot wheel positions let you quickly find harmonically compatible tracks for mixing.

### De-ess

Split-band high-frequency de-esser — attenuates sibilance above `frequency_hz` without affecting the rest of the signal. Implemented with a Butterworth HPF, envelope follower, and per-channel gain reduction. No engine required.

```bash
# Default settings (threshold -20 dB, 6 kHz, 4:1 ratio)
curl -X POST http://localhost:8000/v1/audio/deess \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal.wav","output_path":"out/deessed.wav"}'

# Gentle pass on a mix
curl -X POST http://localhost:8000/v1/audio/deess \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/mix.wav","threshold_db":-15,"frequency_hz":7000,"ratio":2.5,"output_path":"out/mix_deessed.wav"}'

# Stage output under a different path
curl -X POST http://localhost:8000/v1/audio/deess \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal.wav","output_path":"sessions/vocal_deessed.wav"}'
# → {"path":"sessions/vocal_deessed.wav","threshold_db":-20.0,"frequency_hz":6000.0,"ratio":4.0,...}
```

Optional params: `threshold_db` (≤ 0, default -20), `frequency_hz` (2000–15000, default 6000), `ratio` (1.0–20.0, default 4.0), `output_format` (wav/mp3/flac…), `output_path`.

### Stereo field analysis

Measure stereo width, phase correlation, mid/side balance, and mono compatibility. No engine required — pure numpy.

```bash
curl -X POST http://localhost:8000/v1/audio/stereo-field \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/stereo_mix.wav"}' | jq .
# → {
#     "correlation": 0.72,       # Pearson L/R correlation [-1,1]
#     "width": 0.41,             # side_rms / mid_rms
#     "balance_db": -0.3,        # L vs R level difference
#     "mono_compatible": true,   # correlation >= 0.5
#     "mid_level_db": -12.1,
#     "side_level_db": -18.4,
#     "phase_issues": false,
#     "channels": 2,
#     "sample_rate": 44100,
#     "duration": 210.5
#   }

# Analyze a different staged file
curl -X POST http://localhost:8000/v1/audio/stereo-field \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"masters/track.wav"}' | jq '{correlation, width, mono_compatible}'
```

Mono files return `correlation=1.0`, `width=0.0`, `mono_compatible=true`. Use `correlation < 0` as a red flag for phase-cancelled material that will collapse on mono playback.

### Audio thumbnail

Extract the most energetic segment of an audio file — the passage with the highest onset density in a given window. Useful for generating preview clips, podcast teasers, or DJ cue points. Requires `librosa-analyze`.

```bash
# Default 30-second thumbnail
curl -X POST http://localhost:8000/v1/audio/thumbnail \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/long_track.wav","output_path":"out/preview.wav"}'

# 10-second teaser
curl -X POST http://localhost:8000/v1/audio/thumbnail \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/podcast.wav","duration_sec":10,"output_format":"mp3","output_path":"out/teaser.mp3"}'

# Stage + get timestamps
curl -X POST http://localhost:8000/v1/audio/thumbnail \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/album_track.wav","duration_sec":20,"output_path":"previews/track_thumb.wav"}'
# → {"path":"previews/track_thumb.wav","start_sec":47.3,"end_sec":67.3,"duration_sec":20.0,...}
```

Optional params: `duration_sec` (1–300, default 30), `output_format`, `output_path`. When `output_path` is set the response JSON includes `start_sec` and `end_sec` so you know exactly where in the source the thumbnail was extracted.

### MIDI humanize

Add subtle timing and velocity variations to a MIDI file to make it sound less mechanical. Jitter is uniformly distributed and, when a `seed` is provided, fully deterministic. Requires `midi-compose`.

```bash
# Gentle humanize with defaults (±10 ms timing, ±10% velocity)
curl -X POST http://localhost:8000/v1/midi/humanize \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/rigid.mid","output_path":"midi/human.mid"}'

# Heavier feel with a fixed seed for reproducible results
curl -X POST http://localhost:8000/v1/midi/humanize \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/drums.mid","timing_ms":20,"velocity_pct":15,"seed":42,"output_path":"midi/drums_human.mid"}'

# Stage output under a different path
curl -X POST http://localhost:8000/v1/midi/humanize \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/pattern.mid","timing_ms":8,"output_path":"midi/pattern_human.mid"}'
# → {"path":"midi/pattern_human.mid","timing_ms":8.0,"velocity_pct":10.0,...}
```

Optional params: `timing_ms` (0–500, default 10), `velocity_pct` (0–50, default 10), `seed` (any int, optional), `output_path`. Non-MIDI input returns 400. Requires `midi-compose`.

### Batch operations

Run multiple operations on staged files in one HTTP call. Operations run sequentially; each gets an independent result entry even if earlier ops fail.

Supported ops: `convert`, `normalize`, `trim`, `fade`, `reverse`, `speed`, `eq`.

```bash
# Stage input
curl -X PUT http://localhost:8000/v1/files/work/track.wav --data-binary @track.wav

# Batch: trim, convert to MP3, reverse in one call
curl -X POST http://localhost:8000/v1/batch \
  -H "Content-Type: application/json" \
  -d '[
    {"op":"trim","file_path":"work/track.wav","output_path":"work/chorus.wav","start_sec":30,"end_sec":60},
    {"op":"convert","file_path":"work/track.wav","output_path":"work/track.mp3","output_format":"mp3"},
    {"op":"reverse","file_path":"work/track.wav","output_path":"work/reversed.wav"}
  ]' | jq '.results[].status'
# → "ok" "ok" "ok"
```

### Async jobs and webhooks

Every audio endpoint accepts `async_job=true` — the request returns immediately with a job ID and the work happens in the background. Poll for status or register a webhook.

```bash
# Pre-stage input (one-time)
curl -X PUT --data-binary @track.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/track.wav

# Submit async with staging path — result written to /v1/files/stems/...
curl -X POST http://localhost:8000/v1/audio/separate \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path":"uploads/track.wav",
    "engine":"htdemucs",
    "stems":["vocals"],
    "async_job":true,
    "webhook_url":"https://my-server.com/hooks/audio",
    "output_path":"stems/track-vocals.wav"
  }'
# → {"job_id":"abc123","status":"pending","status_url":"/v1/jobs/abc123"}

# Submit async with presigned S3 PUT URL — result uploaded on completion
curl -X POST http://localhost:8000/v1/audio/master \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path":"uploads/track.wav",
    "mode":"chain",
    "preset":"transparent",
    "async_job":true,
    "output_url":"https://bucket.s3.amazonaws.com/result.wav?X-Amz-..."
  }'
# → {"job_id":"def456","status":"pending","status_url":"/v1/jobs/def456"}

# Poll
curl http://localhost:8000/v1/jobs/abc123 | jq '{status, duration_sec, result}'

# List all jobs (optional ?status=pending|running|completed|failed|cancelled)
curl http://localhost:8000/v1/jobs

# Cancel a running job
curl -X DELETE http://localhost:8000/v1/jobs/abc123
```

Webhook payload (POST to your URL when the job completes):

```json
{
  "id": "abc123",
  "endpoint": "/v1/audio/separate",
  "status": "completed",
  "duration_sec": 12.4,
  "result": {"path": "stems/track-vocals.wav", "size": 3145728, ...}
}
```

Delivery has 4 attempts with exponential backoff (0 s, 1 s, 2 s, 4 s). Completed jobs stay in memory for `AUDIOLLA_JOB_TTL` seconds (default 1 hour) then are swept.

### Stage files

A simple server-side file store under `/v1/files`. Upload, list, download, delete.

```bash
# upload
curl -X PUT http://localhost:8000/v1/files/mytrack.wav \
  --data-binary @track.wav

# list
curl http://localhost:8000/v1/files

# download
curl http://localhost:8000/v1/files/mytrack.wav -o copy.wav

# delete
curl -X DELETE http://localhost:8000/v1/files/mytrack.wav
```

Once staged, reference the file by path on any audio endpoint via `file_path`:

```bash
# Analyze a staged file
curl -X POST http://localhost:8000/v1/audio/analyze \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"mytrack.wav","features":["bpm"]}'

# Separate stems and write the result back to staging
curl -X POST http://localhost:8000/v1/audio/separate \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path":"mytrack.wav",
    "engine":"htdemucs",
    "stems":["vocals"],
    "output_path":"stems/mytrack-vocals.wav"
  }'
# → {"path":"stems/mytrack-vocals.wav","size":...,"output_format":"wav",...}
```

### Remote URLs

Disabled by default. To allow the server to fetch `file_url` or PUT to
`output_url`, set the policy at container start:

```bash
docker run ... \
  -e AUDIOLLA_FETCH_MODE=allowlist \
  -e AUDIOLLA_FETCH_HOSTS="*.s3.amazonaws.com,*.r2.cloudflarestorage.com" \
  psyb0t/audiolla:latest
```

Then:

```bash
# Fetch from S3, master, PUT result back to a presigned S3 URL
curl -X POST http://localhost:8000/v1/audio/master \
  -H 'Content-Type: application/json' \
  -d '{
    "file_url":"https://my-bucket.s3.amazonaws.com/in.wav",
    "reference_url":"https://my-bucket.s3.amazonaws.com/ref.wav",
    "mode":"reference",
    "output_url":"https://my-bucket.s3.amazonaws.com/out.wav?X-Amz-Signature=..."
  }'
# → {"url":"...","size":...,"output_format":"wav",...}
```

Policy modes:

- `disabled` (default) — `file_url` / `output_url` rejected with 400
- `allowlist` — only hosts matching `AUDIOLLA_FETCH_HOSTS` allowed
- `denylist` — anything except listed hosts allowed (pair with `AUDIOLLA_FETCH_ALLOW_PRIVATE=false` to block private IPs / metadata services)

Always-on protections:
- DNS-resolved private / loopback / link-local IPs rejected (toggleable)
- Only `https` by default; `http` opt-in via `AUDIOLLA_FETCH_SCHEMES`
- Redirects re-validated through the same policy
- Hard timeout + size cap = `AUDIOLLA_MAX_UPLOAD_BYTES`
- Every fetch / upload URL logged

See [Configuration](#configuration) for all `AUDIOLLA_FETCH_*` env vars.

---

## Engines

| Slug | What it does |
|------|--------------|
| `htdemucs` | 4-stem separation: drums, bass, other, vocals. Best speed/quality tradeoff. |
| `htdemucs_ft` | Same 4 stems, fine-tuned weights. Higher quality, ~4x slower. **CUDA-only** — rejected with 400 on the CPU image. |
| `htdemucs_6s` | 6 stems — also splits guitar and piano. Experimental. |
| `mdx_extra` | Strong on vocal isolation. MUSDB-trained, different architecture. |
| `matchering` | Reference-based mastering: EQ + loudness matched to a reference track. |
| `pedalboard-chain` | Preset mastering chains via pedalboard — `transparent` (light) or `loud` (4:1 squash). Backs `/v1/audio/master` with `mode=chain`. For arbitrary chains use `fx-chain` / `/v1/audio/fx`. |
| `librosa-analyze` | BPM, key, LUFS, duration, spectral features, beat grid, onset detection, melody (pyin), structural segmentation via librosa. |
| `sox-transform` | Gain, EQ, compression, reverb, pitch shift, tempo via pysox. |
| `fx-chain` | Arbitrary pedalboard effects chain — full catalog, your order and params. Backs `/v1/audio/fx`. |
| `midi-compose` | JSON spec → MIDI bytes. Also inspects and transforms existing MIDI files. Backs `/v1/midi/{compose,inspect,transform,generate}`. |
| `midi-render` | MIDI → audio via fluidsynth + SoundFont. Backs `/v1/midi/render` and `/v1/midi/generate`. |
| `silence-detect` | Locate silent gaps via ffmpeg `silencedetect`. Optional auto-trim. Backs `/v1/audio/silence`. |
| `ffmpeg-render` | Static PNG spectrogram/waveform + 8-mode animated MP4/WebM video via ffmpeg filters. Backs `/v1/audio/visualize/image/*` and `/v1/audio/visualize/video/{mode}`. |
| `audio-fingerprint` | Chromaprint acoustic fingerprint via `fpcalc`. Backs `/v1/audio/fingerprint`. |
| `uvr-dereverb` | BS-Roformer de-reverb — removes room reverb; `primary_stem=No Reverb`. |
| `uvr-deecho` | VR Architecture de-echo — normal and aggressive modes; pass `aggressive=true` for harder suppression. |
| `uvr-denoise` | MelBand Roformer de-noise (SDR 28) — removes broadband background noise. |
| `uvr-karaoke` | MelBand Roformer karaoke — remove lead vocals, keep backing; works via `/v1/audio/separate`. |
| `uvr-vocal-bsr` | BS-Roformer vocal/instrumental (SDR 13) — highest-quality vocal separation; works via `/v1/audio/separate`. |
| `basic-pitch` | Polyphonic audio-to-MIDI via Spotify basic-pitch (ONNX backend). Backs `/v1/audio/to_midi`. |
| `deepfilter` | Neural speech and vocal enhancement via DeepFilterNet DF3. Backs `/v1/audio/enhance`. |
| `chord-detect` | Chord and key detection via librosa — Krumhansl-Schmuckler key estimation + chroma template chord segmentation. Backs `/v1/audio/chords`. |
| `silero-vad` | Voice activity detection via silero-vad (ONNX) — returns speech/non-speech segments with timestamps and speech ratio. Backs `/v1/audio/vad`. |
| `pyannote` | Speaker diarization via pyannote/speaker-diarization-3.1 — returns per-speaker timestamped segments. Requires `HUGGINGFACE_TOKEN`. Backs `/v1/audio/diarize`. |
| `stretch` | Time-stretch + pitch-shift via librosa phase vocoder — independent tempo factor and semitone offset. Backs `/v1/audio/stretch`. |
| `ast-tag` | Audio tagging via Audio Spectrogram Transformer (MIT/ast-finetuned-audioset-10-10-0.4593) — top-K AudioSet class labels. Requires HF model cache. Backs `/v1/audio/tag`. |
| `clap-embed` | 512-dim L2-normalized audio embeddings via LAION CLAP (laion/larger_clap_music_and_speech) — semantic audio search. Requires HF model cache. Backs `/v1/audio/embed`. |
| `hpss` | Harmonic/percussive source separation via librosa HPSS median filter — returns harmonic + percussive stems as a ZIP. Backs `/v1/audio/separate/hpss`. |
| `noise-reduce` | Spectral noise reduction via noisereduce — stationary (constant hum/hiss) and non-stationary (adaptive) modes, no GPU required. Backs `/v1/audio/noise-reduce/noise-reduce`. |
| `metadata` | Read/write audio tags (ID3 for MP3, Vorbis for OGG/FLAC, INFO for WAV, MP4 for M4A) via mutagen. No ML weights. Backs `/v1/audio/metadata`. |
| `stable-audio-open` | Text-to-audio — Stability Stable Audio Open 1.0. **Stability Community Licence** (commercial use OK below the revenue threshold; read the license). 47-second hard cap; best for loops, riffs, ambient textures, SFX, drum beats. No vocals. ~12 GB VRAM at fp16 — CUDA-only. Backs `/v1/audio/generate/stable-audio-open`. |
| `musicgen-small` | Text-to-music — Meta MusicGen 300M. **CC-BY-NC 4.0** (non-commercial only; opt-in via `AUDIOLLA_ENABLE_NONCOMMERCIAL=1` in the server env). 30 s hard cap; instrumental only. ~3 GB VRAM at fp16 — CUDA-only. Backs `/v1/audio/generate/musicgen-small`. |
| `musicgen-medium` | Text-to-music — Meta MusicGen 1.5B. **CC-BY-NC 4.0** (same opt-in). 30 s hard cap; higher quality than -small. ~6-8 GB VRAM at fp16 — CUDA-only. Backs `/v1/audio/generate/musicgen-medium`. |
| `riffusion` | Text-to-music — Riffusion-v1, a Stable Diffusion fine-tune that generates spectrograms (converted to audio via Griffin-Lim). **CreativeML OpenRAIL-M** (commercial use OK with the licence's usage restrictions). ~5 s per pass, lo-fi character, 22.05 kHz mono. ~3 GB VRAM at fp16 — CUDA-only. Backs `/v1/audio/generate/riffusion`. |
| `audioldm2` | Text-to-audio / SFX — AudioLDM 2 (cvssp/audioldm2). **CC-BY 4.0** (commercial use OK — no opt-in gate, the only commercial-safe generator in this set). General-purpose SFX: environmental ambience, animal sounds, foley, mechanical / impact sounds. 16 kHz mono, up to 30 s. Slow (200-step DDIM by default — pass `num_inference_steps=50` to trade quality for ~4x speed). ~8-10 GB VRAM at fp16 with CPU offload. CUDA-only. Backs `/v1/audio/generate/audioldm2`. |

Each Demucs variant is its own checkpoint (hosted on `dl.fbaipublicfiles.com`). The entrypoint prefetches every enabled variant into `/data/torch_cache/` at startup so the first separation request doesn't sit there downloading.

`AUDIOLLA_ENABLED_ENGINES` — restrict which engines are available. `AUDIOLLA_PRELOAD` — load specific engines into memory at startup instead of waiting for the first request.

---

## Workflows — presets + pipeline

Two ways to chain operations server-side without re-uploading the audio between calls:

**Curated presets** — server-side YAML workflows shipped in `presets/`. Run one with a single POST:

```bash
# Pre-stage input
curl -X PUT --data-binary @mix.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/mix.wav

# Master a mix for Spotify (-14 LUFS) — multiband compress + normalise
curl -X POST http://localhost:8000/v1/presets/master-for-spotify \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/mix.wav","output_path":"out/mastered.wav"}'
# → {"path":"out/mastered.wav","size":...,"steps":[...]}
curl -o mastered.wav http://localhost:8000/v1/files/out/mastered.wav

# List available presets
curl http://localhost:8000/v1/presets | jq '.data[] | {name, description}'

# Inspect a preset's steps before running
curl http://localhost:8000/v1/presets/podcast-cleanup | jq '.steps'
```

Shipped presets: `master-for-spotify` (3-band master + -14 LUFS), `podcast-cleanup` (DeepFilterNet + de-ess + -16 LUFS), `vocal-cleanup` (UVR dereverb + denoise + de-ess + light comp). Add your own as a YAML file in `presets/`.

**Ad-hoc pipeline** — chain any registered ops in a single call:

```bash
# Restore + multiband + normalise in one request — intermediates stay
# server-side, no re-upload between steps.
curl -X POST http://localhost:8000/v1/pipeline \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path":"uploads/track.wav",
    "output_path":"out/pipelined.wav",
    "steps":[
      {"op":"restore","params":{"engine":"uvr-denoise"}},
      {"op":"multiband_compress","params":{
        "crossovers_hz":[200,3000],
        "bands":[
          {"threshold_db":-18,"ratio":3},
          {"threshold_db":-14,"ratio":2.5},
          {"threshold_db":-10,"ratio":2}
        ]
      }},
      {"op":"normalize","params":{"target_lufs":-14}}
    ]
  }'
# → {"path":"out/pipelined.wav","size":...,"steps":[...]}

# Discover available ops
curl http://localhost:8000/v1/ops | jq .
```

The response of pipeline + preset endpoints includes a `steps` log so you can audit what ran. Both endpoints support `async_job=true`, `output_path`, `output_url` like every other audio-producing endpoint.

## API catalog

`GET /v1/catalog` returns the machine-readable list of every endpoint grouped by category (`separation`, `restoration`, `dynamics`, `eq-spatial`, `mastering`, `time-pitch`, `editing`, `analysis`, `effects-creative`, `visualize`, `midi`, `metadata`, `workflow`, `speech`, `files`, `jobs`, `management`). Use it for discovery; LLM agents and codegen scripts both consume it.

```bash
curl http://localhost:8000/v1/catalog | jq '.categories[] | {name, endpoint_count: (.endpoints | length)}'
```

## Endpoints

Full wire contract: [`openapi.yaml`](openapi.yaml).

### Audio processing

Every endpoint takes a JSON body. Inputs pick exactly one of `file_path`
(pre-staged file under `FILES_DIR`) xor `file_url` (HTTPS URL the server
fetches). Audio-producing endpoints additionally require exactly one of
`output_path` (server writes the result under `FILES_DIR`) xor
`output_url` (presigned PUT — server uploads the encoded bytes). Both
missing → 400; both set → 400. Responses are always JSON — no raw audio
bytes, no `Content-Disposition: attachment`, no `*_base64` fields.

| Method | Path | Default returns |
|--------|------|-----------------|
| `POST` | `/v1/audio/separate` | JSON `{path\|url, size, ...}` — one stem; multi-stem (or all) returns ZIP stream of stems via `output_path`/`output_url` |
| `POST` | `/v1/audio/master` | JSON `{path\|url, size, output_format, ...}` |
| `POST` | `/v1/audio/analyze` | JSON — BPM, key, LUFS, spectral features |
| `POST` | `/v1/audio/beats` | JSON — BPM + beat timestamps; optional click-track WAV |
| `POST` | `/v1/audio/onsets` | JSON — onset timestamps |
| `POST` | `/v1/audio/melody` | JSON — dominant melody contour; optional MIDI export |
| `POST` | `/v1/audio/segments` | JSON — structural segment labels (A, B, C…) |
| `POST` | `/v1/audio/silence` | JSON — silent/non-silent ranges; optional trimmed audio |
| `POST` | `/v1/audio/visualize/image/spectrogram` | JSON `{path\|url, size, ...}` — static PNG spectrogram (`color`, `scale` params) |
| `POST` | `/v1/audio/visualize/image/waveform` | JSON `{path\|url, size, ...}` — static PNG waveform (`color` param) |
| `POST` | `/v1/audio/visualize/video/{mode}` | JSON `{path\|url, size, ...}` — animated MP4/WebM video (8 modes: `spectrum`, `waves`, `cqt`, …) |
| `POST` | `/v1/audio/fingerprint` | JSON — Chromaprint fingerprint string |
| `POST` | `/v1/audio/restore/{engine}` | JSON `{path\|url, size, output_format, ...}` — reverb/echo/noise removed; `aggressive=true` for uvr-deecho hard mode |
| `POST` | `/v1/audio/to_midi/{engine}` | JSON `{path\|url, size, ...}` — polyphonic transcription (MIDI) |
| `POST` | `/v1/audio/enhance/{engine}` | JSON `{path\|url, size, output_format, ...}` — neural speech/vocal enhancement |
| `POST` | `/v1/audio/generate/{engine}` | JSON `{path\|url, size, output_format, ...}` — text-to-audio (engine = `stable-audio-open` / `musicgen-small` / `musicgen-medium` / `riffusion` / `audioldm2`); `prompt` required, optional `duration_sec` / `seed` / `lyrics` / `num_inference_steps` |
| `POST` | `/v1/audio/chords` | JSON — detected key and chord progression |
| `POST` | `/v1/audio/vad` | JSON — speech/non-speech segments with timestamps and speech ratio |
| `POST` | `/v1/audio/diarize/{engine}` | JSON — per-speaker timestamped segments |
| `POST` | `/v1/audio/transform` | JSON `{path\|url, size, output_format, ...}` |
| `POST` | `/v1/audio/loudness` | JSON — `{loudness_lufs}` (measure only, no audio) |
| `POST` | `/v1/audio/loudness/curve` | JSON — `{curve:[{time_sec,rms_db}],duration,sample_rate,points}`; `hop_length` param |
| `POST` | `/v1/audio/normalize` | JSON `{path\|url, size, measured_lufs, ...}` — requires `target_lufs`; pre-normalization LUFS reported in `measured_lufs` field |
| `POST` | `/v1/audio/separate/hpss` | JSON `{path\|url, size, ...}` — ZIP stream containing `harmonic.<fmt>` + `percussive.<fmt>` |
| `POST` | `/v1/audio/noise-reduce/{engine}` | JSON `{path\|url, size, output_format, ...}` — `engine=noise-reduce` (DSP, `stationary`/`prop_decrease`) or `uvr-denoise` (ML) |
| `POST` | `/v1/audio/stretch` | JSON `{path\|url, size, output_format, ...}` |
| `POST` | `/v1/audio/pitch-correct` | JSON `{path\|url, size, output_format, ...}` — `strength` [0.0–1.0]; requires `librosa-analyze` |
| `POST` | `/v1/audio/repair` | JSON `{path\|url, size, output_format, ...}` — `declip` bool, `dehum` bool, `hum_freq` Hz |
| `POST` | `/v1/audio/tag` | JSON — top-K AudioSet labels with confidence scores |
| `POST` | `/v1/audio/embed` | JSON — 512-dim embedding; with `query_text` also returns cosine similarity |
| `POST` | `/v1/audio/classify` | JSON — `{results: [{label, score}]}` sorted descending; requires `clap-embed` |
| `POST` | `/v1/audio/info` | JSON — duration, sample_rate, channels, codec, bit_depth, format |
| `POST` | `/v1/audio/trim` | JSON `{path\|url, size, output_format, ...}` — `start_sec` + `end_sec` required |
| `POST` | `/v1/audio/mix` | JSON `{path\|url, size, output_format, ...}` — `tracks` JSON array required (≥2 entries) |
| `POST` | `/v1/audio/concat` | JSON `{path\|url, size, output_format, ...}` — `files` JSON array required (≥2 entries) |
| `POST` | `/v1/audio/speed` | JSON `{path\|url, size, output_format, ...}` — `speed` float required (0.1–10.0) |
| `POST` | `/v1/audio/convert` | JSON `{path\|url, size, output_format, ...}` — format/sample_rate/channels conversion |
| `POST` | `/v1/audio/similar` | JSON — `{similarity, dim}`; requires `clap-embed` |
| `POST` | `/v1/audio/fade` | JSON `{path\|url, size, output_format, ...}` — `fade_in`/`fade_out` seconds, 13 `curve` options |
| `POST` | `/v1/audio/reverse` | JSON `{path\|url, size, output_format, ...}` — flips playback direction |
| `POST` | `/v1/audio/loop` | JSON `{path\|url, size, output_format, ...}` — `count` total plays (≥2) |
| `POST` | `/v1/audio/bpm-match` | JSON `{path\|url, size, output_format, ...}` — `target_bpm` required; requires `librosa-analyze` + `stretch` |
| `POST` | `/v1/audio/stereo-width` | JSON `{path\|url, size, output_format, ...}` — `width` [0.0–3.0]; M/S stereo processing |
| `POST` | `/v1/audio/split` | JSON `{path\|url, size, ...}` — ZIP stream; `mode=equal` (requires `count`) or `mode=silence` |
| `POST` | `/v1/audio/pan` | JSON `{path\|url, size, output_format, ...}` — `position` [-1.0–1.0] |
| `POST` | `/v1/audio/eq` | JSON `{path\|url, size, output_format, ...}` — `bands` JSON array of `{freq, gain_db, width_hz}` |
| `POST` | `/v1/audio/key-match` | JSON `{path\|url, size, output_format, ...}` — `target_key` required; requires `chord-detect` + `stretch` |
| `POST` | `/v1/audio/sidechain-duck` | JSON `{path\|url, size, output_format, ...}` — primary + `trigger_file_*`; ffmpeg sidechaincompress |
| `POST` | `/v1/audio/fx` | JSON `{path\|url, size, output_format, ...}` |
| `POST` | `/v1/audio/metadata` | JSON — tag fields (title, artist, bpm, key, duration, sample_rate…); writes tags when `tags` JSON is provided |
| `POST` | `/v1/audio/clip-detect` | JSON — clipped, clip_count, clip_ratio, peak_db, duration_sec |
| `POST` | `/v1/audio/mid-side` | JSON `{path\|url, size, output_format, ...}` — `mode=encode` (L/R→M/S) or `mode=decode` (M/S→L/R) |
| `POST` | `/v1/audio/beat-slice` | JSON `{path\|url, size, ...}` — ZIP stream of numbered beat slices; requires `librosa-analyze` |
| `POST` | `/v1/audio/conv-reverb` | JSON `{path\|url, size, output_format, ...}` — `ir_file_path` / `ir_file_url` required; `wet_mix` [0.0–1.0] |
| `POST` | `/v1/audio/transient` | JSON `{path\|url, size, output_format, ...}` — `attack_gain_db` + `sustain_gain_db` |
| `POST` | `/v1/audio/multiband-compress` | JSON `{path\|url, size, output_format, ...}` — N-band compressor; `crossovers_hz` + `bands` JSON arrays |
| `POST` | `/v1/audio/dj-prep` | JSON — bpm, key, camelot, integrated_lufs; requires `librosa-analyze` + `chord-detect` |
| `POST` | `/v1/audio/loop-point` | JSON — `{loop_start_sec,loop_end_sec,bars,score,tempo_bpm,candidates}`; requires `librosa-analyze` |
| `POST` | `/v1/audio/chords-to-midi` | JSON `{path\|url, size, ...}` — chord progression from audio (MIDI); requires `chord-detect` |
| `POST` | `/v1/audio/deess` | JSON `{path\|url, size, output_format, ...}` — split-band sibilance attenuation; `threshold_db`, `frequency_hz`, `ratio` |
| `POST` | `/v1/audio/stereo-field` | JSON — `{correlation, width, balance_db, mono_compatible, mid_level_db, side_level_db, phase_issues, …}` |
| `POST` | `/v1/audio/thumbnail` | JSON `{path\|url, size, start_sec, end_sec, ...}` — most energetic `duration_sec` segment; requires `librosa-analyze` |

### Workflow — presets, pipeline, catalog

Server-side multi-step chains + discovery. See [Workflows](#workflows--presets--pipeline) for narrative + curl examples.

| Method | Path | |
|--------|------|-|
| `GET`  | `/v1/catalog` | machine-readable endpoint list grouped by category (17 categories) |
| `GET`  | `/v1/ops` | list of pipeline op slugs (~24) usable in presets + `/v1/pipeline` |
| `GET`  | `/v1/presets` | list curated server-side workflows (name + description) |
| `GET`  | `/v1/presets/{name}` | describe one preset including all steps |
| `POST` | `/v1/presets/{name}` | JSON `{path\|url, size, steps, ...}` — run a curated preset; response includes a `steps` audit log of each op executed |
| `POST` | `/v1/pipeline` | JSON `{path\|url, size, steps, ...}` — ad-hoc `steps=[{op, params}, …]` chain, server-side intermediates; response includes a `steps` audit log |

### Batch

| Method | Path | |
|--------|------|-|
| `POST` | `/v1/batch` | JSON body: array of op objects `{op, file_path, output_path, …}`. Returns `{results:[…]}` — errors per-op, not a 4xx. Supported ops: `convert`, `normalize`, `trim`, `fade`, `reverse`, `speed`, `eq`. |

### Async jobs

Every audio endpoint accepts `"async_job": true` in the JSON body. Optional `"webhook_url"` for push-style delivery. When `async_job=true`, the endpoint returns HTTP 202 with `{job_id, status: "pending", status_url}` instead of executing inline.

| Method | Path | |
|--------|------|-|
| `GET` | `/v1/jobs` | list jobs; optional `?status=pending\|running\|completed\|failed\|cancelled` |
| `GET` | `/v1/jobs/{job_id}` | poll one job — returns status, result, duration_sec |
| `DELETE` | `/v1/jobs/{job_id}` | cancel running job or remove completed job |

### MIDI

| Method | Path | Default returns |
|--------|------|-----------------|
| `POST` | `/v1/midi/compose` | JSON `{path\|url, size, ...}` — body is JSON song spec; writes MIDI |
| `POST` | `/v1/midi/inspect` | JSON — tempo, tracks, channels, note counts, time/key signatures |
| `POST` | `/v1/midi/transform` | JSON `{path\|url, size, ...}` — transpose, quantize, tempo override, channel filter; writes MIDI |
| `POST` | `/v1/midi/quantize` | JSON `{path\|url, size, ...}` — `grid_beats` snaps all note timings to a rhythmic grid; writes MIDI |
| `POST` | `/v1/midi/render` | JSON `{path\|url, size, output_format, ...}` — input MIDI via `file_path` / `file_url`; writes audio |
| `POST` | `/v1/midi/generate` | JSON `{path\|url, size, output_format, ...}` — body is JSON song spec (compose + render in one); writes audio |
| `POST` | `/v1/midi/drum` | JSON `{path\|url, size, ...}` — body is JSON step-sequencer spec; writes MIDI; requires `midi-compose` |
| `POST` | `/v1/midi/humanize` | JSON `{path\|url, size, ...}` — timing + velocity jitter; `timing_ms`, `velocity_pct`, `seed`; writes MIDI; requires `midi-compose` |

### File staging

| Method | Path | |
|--------|------|-|
| `GET` | `/v1/files` | list staged files |
| `PUT` | `/v1/files/{path}` | upload |
| `GET` | `/v1/files/{path}` | download |
| `DELETE` | `/v1/files/{path}` | delete |

### Management

| Method | Path | |
|--------|------|-|
| `GET` | `/healthz` | liveness — always unauthenticated |
| `GET` | `/v1/engines` | list configured engines + `loaded` / `idle_seconds` per engine |
| `GET` | `/v1/ps` | list engines in memory right now |
| `DELETE` | `/v1/ps/{engine}` | evict one engine |
| `POST` | `/v1/unload` | evict everything |

---

## MCP

audiolla exposes a [Model Context Protocol](https://modelcontextprotocol.io) server at `/v1/mcp`. Point any MCP-capable LLM agent at it and it gets the full audio processing surface as callable tools — separate stems, detect chords, transcribe to MIDI, diarize speakers, compose music from a JSON spec, read/write tags, submit async jobs — all over JSON-RPC without writing a line of integration code.

Audio-producing MCP tools follow the same contract as REST: callers MUST pass exactly one of **`output_path`** (server writes the result under `FILES_DIR`; client retrieves it via the `get_file` tool or HTTP `GET /v1/files/<path>`; response is `{path, size, ...}`) xor **`output_url`** (presigned PUT — server uploads the encoded bytes to the URL; response is `{url, size, ...}`). Both missing → `ValueError`; both set → `ValueError`. Inline base64 audio responses are gone in v1.0.0 — no `audio_base64` / `midi_base64` / `image_base64` / `video_base64` / `zip_base64` fields exist anymore. Use `list_jobs` / `get_job` / `cancel_job` to manage long-running async work.

**Endpoint:** `http://localhost:8000/v1/mcp`

**Tools:**

| Tool | What it does |
|------|--------------|
| `list_engines` | List configured engines and whether they're loaded |
| `list_presets` | List curated server-side workflows (name + description) |
| `describe_preset` | Show full step list of a preset before running |
| `list_ops` | List the ~24 pipeline op slugs available in `run_pipeline_tool` / presets |
| `run_preset` | Run a curated preset against an input file |
| `run_pipeline_tool` | Run an ad-hoc `[{op, params}, …]` chain server-side |
| `generate_music` | Text-to-audio — `engine` = `stable-audio-open` / `musicgen-small` / `musicgen-medium` / `riffusion` / `audioldm2`; `prompt` required, optional `lyrics`, `duration_sec`, `seed`. MusicGen requires `AUDIOLLA_ENABLE_NONCOMMERCIAL=1`. AudioLDM 2 is CC-BY 4.0 — commercial-safe with no opt-in. |
| `separate` | Demucs stem separation — per-stem staging via `output_paths={stem:path}` xor per-stem PUT via `output_urls={stem:url}` |
| `master` | Reference mastering (matchering) or preset chain (pedalboard) |
| `analyze` | BPM, key, LUFS, spectral features via librosa |
| `beats` | Beat grid — BPM + timestamps; optional click-track audio |
| `onsets` | Note onset timestamps |
| `melody` | Dominant melody contour in Hz; optional MIDI export |
| `segments` | Structural segmentation — recurring section labels (A, B, C…) |
| `silence` | Detect silent gaps; optional auto-trim (edges or all) |
| `visualize` | PNG spectrogram/waveform or animated MP4/WebM — `engine` + `mode` select output type |
| `fingerprint` | Chromaprint acoustic fingerprint (AcoustID-compatible) |
| `restore` | Remove reverb/echo/noise via UVR — `engine` selects model; `aggressive=true` for harder echo suppression |
| `denoise` | Thin shim — prefer `restore` with `engine=uvr-denoise` or `noise_reduce` with `engine=uvr-denoise` |
| `audio_to_midi` | Polyphonic audio-to-MIDI transcription via basic-pitch (ONNX) — writes MIDI to `output_path` xor `output_url` |
| `enhance` | Neural speech and vocal enhancement via DeepFilterNet DF3 |
| `chords` | Chord and key detection via librosa — key + per-segment chord labels |
| `vad` | Voice activity detection via silero-vad — speech/non-speech segments with timestamps |
| `diarize` | Speaker diarization via pyannote — per-speaker timestamped segments |
| `transform` | Sox DSP chain — gain, EQ, reverb, pitch, tempo, etc. |
| `loudness` | Measure integrated LUFS — returns JSON only |
| `loudness_curve` | RMS envelope over time — `{curve:[{time_sec,rms_db}],duration,sample_rate,points}` |
| `normalize` | Normalize audio to a target LUFS level — writes to `output_path` xor `output_url` |
| `hpss` | Harmonic/percussive separation — writes per-stem audio to `output_paths={stem:path}` xor `output_urls={stem:url}` |
| `noise_reduce` | Noise reduction — `engine=noise-reduce` (DSP, stationary/prop_decrease) or `engine=uvr-denoise` (ML) |
| `stretch` | Time-stretch + pitch-shift via librosa phase vocoder |
| `pitch_correct` | Auto-tune toward nearest chromatic semitone — `strength` [0.0–1.0]; requires `librosa-analyze` |
| `repair_audio` | Declip + dehum — `declip` bool, `dehum` bool, `hum_freq` Hz |
| `tag` | Audio tagging via AST — top-K AudioSet labels with confidence scores |
| `embed` | 512-dim CLAP audio embedding; with `query_text` returns cosine similarity |
| `classify` | Zero-shot CLAP classification — cosine similarity against any list of text labels |
| `info` | Probe audio metadata — duration, sample_rate, channels, codec, bit_depth |
| `trim` | Cut audio to [start_sec, end_sec) — writes to `output_path` xor `output_url` |
| `mix` | Mix N tracks with per-track gain — `tracks` list of {file_path/url, gain_db} |
| `concat` | Stitch N audio files end-to-end in order — `files` list of {file_path/url} |
| `speed` | Change playback speed without pitch shift — `speed` float (0.1–10.0) |
| `convert` | Re-encode: format, sample_rate, channels in one call |
| `similar` | Cosine similarity between two audio files via CLAP — returns `{similarity, dim}` |
| `midi_quantize` | Snap MIDI note timings to a rhythmic grid — `grid_beats` in beats |
| `fade` | Fade-in/fade-out with configurable duration and curve shape |
| `reverse` | Flip audio backwards |
| `loop` | Repeat audio N times — `count` total plays |
| `bpm_match` | Detect BPM then stretch to `target_bpm` — returns source/target BPM + tempo_factor |
| `stereo_width` | M/S stereo width — `width=0` mono, `1` original, `>1` wider |
| `split` | Split into equal parts or on silence — MCP form deprecated in v1.0.0; use REST `POST /v1/audio/split` with `output_path` for per-segment staging |
| `pan` | Pan in the stereo field — `position` [-1.0–1.0] |
| `eq` | Parametric EQ — `bands` list of `{freq, gain_db, width_hz}` |
| `key_match` | Detect key then pitch-shift to `target_key` — returns source_key + semitones |
| `sidechain_duck` | Duck primary track on trigger — `threshold_db`, `ratio`, `attack_ms`, `release_ms` |
| `fx` | Generic pedalboard effects chain — full catalog, your order and params |
| `midi_compose` | JSON song spec → MIDI; writes to `output_path` xor `output_url` |
| `midi_inspect` | Read MIDI structure — tempo, tracks, channels, note counts |
| `midi_transform` | Transpose, quantize, tempo override, channel filter on an existing MIDI file |
| `midi_render` | MIDI → audio via fluidsynth + SoundFont |
| `midi_generate` | One-shot compose + render — spec in, audio out |
| `drum_pattern` | Step-sequencer JSON spec → GM drum MIDI; `pattern` object of voice arrays, `swing`, `steps`, `bars` |
| `chords_to_midi` | Chord progression detected from audio → MIDI file; `tempo_bpm`, `velocity`, `octave` params |
| `audio_metadata` | Read or write audio tags — pass `tags` dict to write, omit to read |
| `detect_clipping` | Report digital clipping — clipped, clip_count, clip_ratio, peak_db |
| `mid_side` | M/S encode (`mode=encode`) or decode (`mode=decode`) stereo audio |
| `slice_at_beats` | Slice audio at beat positions — writes zip archive to `output_path` xor `output_url`; response includes `beat_count` |
| `convolution_reverb` | Apply IR reverb — `ir_file_path`/`ir_file_url` + `wet_mix` [0.0–1.0] |
| `transient_shaper` | Attack/sustain shaping — `attack_gain_db`, `sustain_gain_db` |
| `multiband_compress` | N-band compressor — `crossovers_hz` list + `bands` list of per-band specs |
| `dj_prep` | BPM + key + Camelot wheel + LUFS in one call |
| `find_loop_point` | Find best seamless loop boundary — `{loop_start_sec,loop_end_sec,bars,score,tempo_bpm,candidates}` |
| `deess` | Split-band sibilance attenuation — `threshold_db`, `frequency_hz`, `ratio` |
| `stereo_field` | Stereo field analysis — correlation, width, balance_db, mono_compatible, mid/side levels |
| `audio_thumbnail` | Extract most energetic segment — `duration_sec`; writes to `output_path` xor `output_url`; response includes `start_sec`/`end_sec` |
| `midi_humanize` | Add timing + velocity jitter to MIDI — `timing_ms`, `velocity_pct`, optional `seed` for deterministic output |
| `list_jobs` | List async jobs; optional `status` filter |
| `get_job` | Poll one async job by `job_id` |
| `cancel_job` | Cancel a running job or remove a completed one |
| `list_files` | List staged files |
| `put_file` | Upload a file (base64) to the staging area |
| `get_file` | Read a staged file back (base64) |
| `delete_file` | Remove a staged file |

Auth (`AUDIOLLA_AUTH_TOKEN`) covers `/v1/mcp` the same as the REST endpoints — pass the bearer token in the `Authorization` header.

---

## Configuration

| Variable | Default | |
|----------|---------|-|
| `AUDIOLLA_DEVICE` | `auto` | `auto`, `cpu`, `cuda`, or `cuda:N` |
| `AUDIOLLA_ENGINES_FILE` | `/app/engines.json` | path to engines registry |
| `AUDIOLLA_PRESETS_DIR` | `/app/presets` | directory of `*.yaml` preset workflows loaded at startup |
| `AUDIOLLA_DATA_DIR` | `/data` | where models and staged files live |
| `AUDIOLLA_UVR_MODELS_DIR` | `<DATA_DIR>/uvr_models` | where UVR model files are cached |
| `AUDIOLLA_AUTH_TOKEN` | — | bearer token; empty means no auth |
| `HUGGINGFACE_TOKEN` | — | HuggingFace access token; required for `pyannote` speaker diarization (accept model terms at huggingface.co/pyannote/speaker-diarization-3.1 first) |
| `AUDIOLLA_ENABLED_ENGINES` | _(all)_ | comma-separated slugs to allow; empty = all |
| `AUDIOLLA_PRELOAD` | — | comma-separated slugs to load at startup |
| `AUDIOLLA_ENGINE_TTL` | `600` | seconds idle before an engine is unloaded (`10m` also works) |
| `AUDIOLLA_SWEEPER_INTERVAL` | `60` | how often the idle sweeper checks, in seconds |
| `AUDIOLLA_MAX_UPLOAD_BYTES` | `209715200` | upload cap (200 MB) — also caps URL fetch body size |
| `AUDIOLLA_FETCH_MODE` | `disabled` | `disabled`, `allowlist`, or `denylist` — controls server-side fetching for file_url / output_url |
| `AUDIOLLA_FETCH_HOSTS` | _(none)_ | comma-separated host patterns (`bucket.s3.amazonaws.com`, `*.s3.amazonaws.com`). Required when mode=allowlist. |
| `AUDIOLLA_FETCH_SCHEMES` | `https` | comma-separated schemes — `https`, `http` (http opt-in only) |
| `AUDIOLLA_FETCH_ALLOW_PRIVATE` | `false` | allow URLs that resolve to private / loopback / link-local IPs |
| `AUDIOLLA_FETCH_TIMEOUT` | `30` | hard timeout per fetch/upload, in seconds (also accepts `30s`, `1m`) |
| `AUDIOLLA_FETCH_MAX_REDIRECTS` | `5` | max redirects per fetch; each Location re-validated through the policy |
| `AUDIOLLA_JOB_TTL` | `3600` | Seconds a completed/failed/cancelled job stays in memory before being swept. Also accepts `1h`, `30m`. |
| `AUDIOLLA_JOB_MAX_CONCURRENT` | `8` | Maximum number of async jobs that can run simultaneously. |
| `AUDIOLLA_SOUNDFONT` | `/usr/share/sounds/sf2/FluidR3_GM.sf2` (prod images) | Default SoundFont path for `/v1/midi/render`. Override per request via `soundfont_path`. |

---

## What's not in here

| | Why |
|-|-----|
| MusicGen / MAGNeT / JASCO | CC-BY-NC weights. Outclassed by ACE-Step (Apache 2.0) and DiffRhythm (Apache 2.0), both shipping in the box as of v1.0.0. |
| YuE 7B | Apache 2.0 but realistically needs 16-24 GB VRAM at fp16; doesn't fit comfortably on a 12 GB GPU without int4 quant tooling. Revisit when a 2B or quantised variant lands. |
| Essentia analysis | AGPL v3 — any network service using it has to publish full source. librosa handles the common cases without that. |
| Streaming separation | Demucs needs the whole file. No chunked or real-time inference. |
| VST3 plugin hosting | Pedalboard can do it but you'd need to mount your host plugin directory. Out of scope for the default image. |
| rubberband pitch/time-stretch | GPL v2 + commercial license. Sox handles basic pitch and tempo. Add it yourself if you accept the terms. |

---

## Build & dev

```bash
make build        # CPU image
make build-cuda   # CUDA image
make run          # CPU image on port 8000
make run-cuda     # CUDA image on port 8000
```

```bash
make dev-image          # build the dev container
make shell              # shell inside it
make lint               # flake8 + mypy
make format             # isort + black
make test-unit          # unit tests (no GPU, no ML deps needed)
make test-unit-cov-gate # fail if coverage on support modules drops below 80%
make test-integration   # integration tests (spins up Docker containers)
make generate           # regenerate src/audiolla/schema/ from openapi.yaml
make clean              # wipe build/cache artifacts
```

```bash
make pkg-lock                 # refresh uv.lock
make pkg-add PKG=name[==ver]  # add a dep
make pkg-update PKG=name      # upgrade one dep
make pkg-upgrade              # upgrade everything
make pkg-remove PKG=name      # remove a dep
make pkg-compile-heavy        # recompile requirements-heavy-{cpu,cuda}.txt
```

Every `make pkg-*` bumps `[tool.uv] exclude-newer` to UTC midnight **7 days before** the bump date before touching anything — packages published in the last week are invisible to the resolver. The 7-day floor is the supply-chain attack window: fresh wheels (typosquats, hijacked maintainer releases) typically get caught and yanked within hours-to-days, so the floor gives malicious uploads a week of community scrutiny before they're eligible to enter the lockfile. Everything runs inside the dev container. Host needs `docker`, `make`, `git`.

---

## Supply chain

Both prod images do a two-layer install.

**Light deps** (`fastapi`, `uvicorn`, `pydantic`, etc.): locked in `uv.lock`, installed with `uv sync --frozen --no-dev`. Build fails if the lockfile doesn't match `pyproject.toml`. Wheel hashes verified by uv.

**Heavy ML/DSP deps** (torch, demucs, matchering, pedalboard, librosa, sox, numpy, soundfile, huggingface-hub): one hash-locked requirements file per image variant (`requirements-heavy-cpu.txt`, `requirements-heavy-cuda.txt`), because the torch wheel differs between CPU and CUDA and lives on a different index. Human specs in `scripts/heavy-deps-{cpu,cuda}.in`, compiled via `make pkg-compile-heavy`, installed with `uv pip install --require-hashes`. Both files are committed.

Base images and the `uv` binary pinned by `@sha256:` digest.

---

## License

[WTFPL](LICENSE).

matchering and pedalboard are GPL v3. Fine for self-hosted use. Distributing the image as a product needs a GPL compliance review.
