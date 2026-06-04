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
| 🎛️ **DJ prep** | One call: BPM + key + Camelot wheel position + integrated LUFS |
| 📦 **Batch** | Run trim/convert/fade/reverse/speed/eq on staged files in sequence |
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
  - [Spectrogram, waveform, visualise](#spectrogram-waveform-visualise)
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
  - [DJ prep](#dj-prep)
  - [Batch operations](#batch-operations)
  - [Async jobs and webhooks](#async-jobs-and-webhooks)
  - [Stage files](#stage-files)
  - [Remote URLs](#remote-urls)
- [Engines](#engines)
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

## Quick start

Once the container is up, this is a complete audio pipeline in six curl commands:

```bash
# rip the vocals out of a track
curl -X POST http://localhost:8000/v1/audio/separate \
  -F "file=@song.wav" -F "engine=htdemucs" -F "stems=vocals" \
  -o vocals.wav

# what key is it in? what are the chords?
curl -X POST http://localhost:8000/v1/audio/chords -F "file=@song.wav"
# → {"key":"F# minor","key_confidence":0.91,"chords":[{"chord":"F#m","start_sec":0.0,...},...]}

# transcribe that vocal melody to MIDI
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -F "file=@vocals.wav" -o melody.mid

# render the MIDI back to audio through a SoundFont
curl -X POST http://localhost:8000/v1/midi/render \
  -F "file=@melody.mid" -o rendered.wav

# strip background noise from a voice recording
curl -X POST http://localhost:8000/v1/audio/denoise/uvr-denoise \
  -F "file=@interview.wav" -o clean.wav

# who's speaking and when?
curl -X POST http://localhost:8000/v1/audio/diarize/pyannote \
  -F "file=@interview.wav"
# → {"num_speakers":2,"segments":[{"speaker":"SPEAKER_00","start_sec":0.5,"end_sec":8.2},...]}
```

Audio in. MIDI out. Chords detected. Speakers identified. De-noised. Re-synthesized. No Python environment to set up. No API keys. No account. Just HTTP.

---

## What it can do

Output defaults to `wav`. Pass `-F "output_format=mp3"` to get mp3 instead (`flac`, `opus`, `aac`, `pcm` also work).

**Input** — every audio endpoint accepts exactly one of:

- `file` — multipart upload (the default in the examples below)
- `file_path` — path inside the `/v1/files` staging area
- `file_url` — remote URL the server fetches (disabled by default — see [Remote URLs](#remote-urls))

**Output** — audio-producing endpoints also accept:

- `output_path` — server writes to `/v1/files/<path>`, returns JSON
- `output_url` — server PUTs to a presigned URL, returns JSON
- neither → raw audio bytes (the default)

### Split stems

```bash
# vocals only
curl -X POST http://localhost:8000/v1/audio/separate \
  -F "file=@track.wav" \
  -F "engine=htdemucs" \
  -F "stems=vocals" \
  -o vocals.wav

# all 4 stems as a ZIP
curl -X POST http://localhost:8000/v1/audio/separate \
  -F "file=@track.wav" \
  -F "engine=htdemucs" \
  -o stems.zip
```

### Master

```bash
# match EQ + loudness to a reference track
curl -X POST http://localhost:8000/v1/audio/master \
  -F "file=@track.wav" \
  -F "mode=reference" \
  -F "reference=@ref.wav" \
  -o mastered.wav

# run a built-in pedalboard chain (presets: transparent, loud)
curl -X POST http://localhost:8000/v1/audio/master \
  -F "file=@track.wav" \
  -F "mode=chain" \
  -F "preset=loud" \
  -o mastered.wav
```

### Analyze

```bash
# returns JSON. features: bpm, key, loudness, duration,
# spectral_centroid, rms, zcr. Omit features= to get them all.
curl -X POST http://localhost:8000/v1/audio/analyze \
  -F "file=@track.wav" \
  -F "features=bpm" \
  -F "features=key" \
  -F "features=loudness"
```

### Beats, onsets, melody, segments

```bash
# beat grid — returns bpm + beat timestamps
curl -X POST http://localhost:8000/v1/audio/beats \
  -F "file=@track.wav"

# onset timestamps — note attacks, transients
curl -X POST http://localhost:8000/v1/audio/onsets \
  -F "file=@track.wav"

# dominant melody contour — pitch in Hz per frame
curl -X POST http://localhost:8000/v1/audio/melody \
  -F "file=@track.wav"

# structural segmentation — labels recurring sections A, B, C...
curl -X POST http://localhost:8000/v1/audio/segments \
  -F "file=@track.wav" \
  -F "num_segments=4"
```

Beat detection also generates a click-track file when `click_track=true` — handy for aligning a mix to a grid. Pass `start_bpm=140` to seed the tracker when you already know the rough tempo (faster, more accurate). Melody can be exported as a single-track MIDI file via `as_midi=true`.

### Silence detection and trimming

```bash
# find silent gaps in a recording
curl -X POST http://localhost:8000/v1/audio/silence \
  -F "file=@track.wav" \
  -F "threshold_db=-30" \
  -F "min_duration_sec=1.0"

# trim all silence and get a shorter file back
curl -X POST http://localhost:8000/v1/audio/silence \
  -F "file=@track.wav" \
  -F "threshold_db=-30" \
  -F "min_duration_sec=0.5" \
  -F "trim_mode=all" \
  -o trimmed.wav

# trim only leading/trailing silence, write to staging
curl -X POST http://localhost:8000/v1/audio/silence \
  -F "file=@track.wav" \
  -F "threshold_db=-40" \
  -F "min_duration_sec=0.3" \
  -F "trim_mode=edges" \
  -F "output_path=processed/trimmed.wav"
```

`trim_mode=edges` — chop leading + trailing silence only. `trim_mode=all` — remove every detected gap (compress a talk recording, tighten a loop). Without `trim_mode`, the response is JSON only: `silent_ranges`, `non_silent_ranges`, `duration`.

### Spectrogram, waveform, visualise

```bash
# static PNG spectrogram
curl -X POST http://localhost:8000/v1/audio/spectrogram \
  -F "file=@track.wav" \
  -F "width=1280" \
  -F "height=720" \
  -o spec.png

# static PNG waveform
curl -X POST http://localhost:8000/v1/audio/waveform \
  -F "file=@track.wav" \
  -F "width=1280" \
  -F "height=240" \
  -o wave.png

# animated MP4 spectrum analyser
curl -X POST http://localhost:8000/v1/audio/visualize \
  -F "file=@track.wav" \
  -F "mode=spectrum" \
  -F "width=1280" \
  -F "height=720" \
  -F "fps=30" \
  -F "container=mp4" \
  -o viz.mp4
```

`visualize` modes: `spectrum` (scrolling FFT), `waves` (oscilloscope), `cqt` (constant-Q transform), `freqs` (bar-graph analyzer), `volume` (VU meter), `vectorscope` (stereo X/Y scope), `phasemeter`, `histogram`. Containers: `mp4`, `webm`.

### Acoustic fingerprint

```bash
# Chromaprint fingerprint — identifies a recording regardless of encoding
curl -X POST http://localhost:8000/v1/audio/fingerprint \
  -F "file=@track.wav"
# → {"duration": 215.34, "fingerprint": "AQADtEqRRIuQ..."}

# include the raw integer array (for custom similarity scoring)
curl -X POST http://localhost:8000/v1/audio/fingerprint \
  -F "file=@track.wav" \
  -F "return_raw=true"
```

The base64 fingerprint string is compatible with the [AcoustID](https://acoustid.org) lookup service.

### De-reverb, de-echo, de-noise

AI audio restoration via UVR ecosystem models — BS-Roformer and MelBand Roformer. These operate on the signal itself, not silence thresholds.

The engine slug is part of the URL path — pick the one you want:

```bash
# Remove room reverb (BS-Roformer, SDR 19+)
curl -X POST http://localhost:8000/v1/audio/dereverb/uvr-dereverb \
  -F "file=@track.wav" \
  -o dry.wav

# Remove echo — normal or aggressive variant
curl -X POST http://localhost:8000/v1/audio/deecho/uvr-deecho \
  -F "file=@track.wav" -o noecho.wav
curl -X POST http://localhost:8000/v1/audio/deecho/uvr-deecho-aggressive \
  -F "file=@track.wav" -o noecho.wav

# Remove broadband background noise (MelBand Roformer, SDR 28)
curl -X POST http://localhost:8000/v1/audio/denoise/uvr-denoise \
  -F "file=@track.wav" \
  -o clean.wav
```

All three support `output_format`, `output_path`, `output_url`.

UVR engines also work through `/v1/audio/separate` — `uvr-vocal-bsr` (BS-Roformer, SDR 13) and `uvr-karaoke` return vocal + instrumental stems like Demucs but often with higher quality.

### Audio-to-MIDI transcription

Polyphonic audio-to-MIDI via Spotify's basic-pitch (ONNX backend, no TensorFlow). Play guitar, hum a melody, record a piano riff — get a MIDI file back with all the notes.

```bash
# Any audio → MIDI bytes
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -F "file=@guitar_riff.wav" \
  -o riff.mid

# Tune the detection thresholds
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -F "file=@piano.wav" \
  -F "onset_threshold=0.6" \
  -F "frame_threshold=0.3" \
  -F "minimum_note_length_ms=80" \
  -o piano.mid

# Write directly to staging
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -F "file_path=recordings/bass.wav" \
  -F "output_path=midi/bass_notes.mid"
# → {"path":"midi/bass_notes.mid","size":...,"engine":"basic-pitch","output_format":"mid"}
```

Optional params: `onset_threshold` (0–1, default 0.5), `frame_threshold` (0–1, default 0.3), `minimum_note_length_ms` (default 58), `minimum_frequency` / `maximum_frequency` (Hz, default unconstrained), `multiple_pitch_bends` (bool, default false), `melodia_trick` (bool, default true — helps with melodic content). Default engine: `basic-pitch`.

The MIDI file is piped straight into `/v1/midi/inspect` or `/v1/midi/render` — audio → MIDI → audio is a complete round-trip.

### Neural speech and vocal enhancement

DeepFilterNet DF3 — deep learning noise suppression trained on speech. Better than broadband de-noise for voice recordings; more surgical than UVR's de-noise on vocals specifically.

```bash
# Enhance a vocal recording
curl -X POST http://localhost:8000/v1/audio/enhance/deepfilter \
  -F "file=@vocal_recording.wav" \
  -o enhanced.wav

# Stage the output, mp3
curl -X POST http://localhost:8000/v1/audio/enhance/deepfilter \
  -F "file_path=vocals/raw.wav" \
  -F "output_format=mp3" \
  -F "output_path=vocals/enhanced.mp3"
```

Supports `output_format`, `output_path`, `output_url`.

### Chord and key detection

Krumhansl-Schmuckler key estimation + chroma-template chord segmentation via librosa. No extra deps beyond the librosa stack.

```bash
curl -X POST http://localhost:8000/v1/audio/chords \
  -F "file=@track.wav"
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
  -F "file=@track.wav" \
  -F "hop_length=256"
```

Optional params: `hop_length` (default 512), `segment_min_duration_sec` (default 0.5 — merge very short chord segments).

### Voice activity detection

silero-vad — ONNX-based VAD, fast and accurate on both speech and music. Returns timestamped speech and non-speech segments.

```bash
curl -X POST http://localhost:8000/v1/audio/vad \
  -F "file=@interview.wav"
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
  -F "file=@podcast.wav" \
  -F "threshold=0.7" \
  -F "min_speech_duration_ms=300" \
  -F "min_silence_duration_ms=200"
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
  -F "file=@interview.wav"
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
  -F "file=@roundtable.wav" \
  -F "num_speakers=4"

# Or constrain the range
curl -X POST http://localhost:8000/v1/audio/diarize/pyannote \
  -F "file=@panel.wav" \
  -F "min_speakers=2" \
  -F "max_speakers=6"
```

Optional params: `num_speakers` (exact count hint), `min_speakers`, `max_speakers`.

### Transform

```bash
# pitch shift up 2 semitones + add reverb, export mp3.
# operations is a JSON array — ops: gain, equalizer, compand, reverb,
# pitch, tempo, rate, channels, trim, pad.
curl -X POST http://localhost:8000/v1/audio/transform \
  -F "file=@track.wav" \
  -F 'operations=[{"op":"pitch","params":{"n_semitones":2}},{"op":"reverb","params":{"reverberance":50}}]' \
  -F "output_format=mp3" \
  -o out.mp3
```

### Loudness measurement

```bash
# Measure integrated LUFS — returns JSON, no audio output
curl -X POST http://localhost:8000/v1/audio/loudness \
  -F "file=@track.wav"
# → {"loudness_lufs": -18.4}
```

### Loudness curve

RMS envelope over time — returns a list of `{time_sec, rms_db}` points. Useful for generating gain automation curves, finding loud and quiet sections, or visualising dynamic range before mastering.

```bash
# Default hop (512 samples) — fine-grained envelope
curl -X POST http://localhost:8000/v1/audio/loudness-curve \
  -F "file=@track.wav" | jq '.curve[:5]'
# → [
#     {"time_sec": 0.0,   "rms_db": -18.4},
#     {"time_sec": 0.012, "rms_db": -17.9},
#     ...
#   ]

# Coarser envelope (2048-sample hop)
curl -X POST http://localhost:8000/v1/audio/loudness-curve \
  -F "file=@track.wav" \
  -F "hop_length=2048" | jq '{duration, sample_rate, points}'
```

Response fields: `curve` (array of `{time_sec, rms_db}`), `duration` (seconds), `sample_rate`, `points` (total curve length). Optional param: `hop_length` (default 512).

### Loudness normalization

```bash
# Normalize to -14 LUFS (streaming platform standard) — returns audio
curl -X POST http://localhost:8000/v1/audio/normalize \
  -F "file=@track.wav" \
  -F "target_lufs=-14" \
  -o normalized.wav

# Write to staging, check measured LUFS from header
curl -X POST http://localhost:8000/v1/audio/normalize \
  -F "file=@track.wav" \
  -F "target_lufs=-23" \
  -F "output_path=mastered/norm.wav"
```

`target_lufs` is required. The response carries `X-Loudness-LUFS` with the measured pre-normalization level.

### HPSS (harmonic/percussive split)

Median-filter harmonic/percussive source separation via librosa. Harmonic = tonal content (pitched instruments, pads); percussive = transients (drums, percussion). No ML — pure DSP, fast, no GPU needed.

```bash
# Get both stems in a ZIP
curl -X POST http://localhost:8000/v1/audio/hpss \
  -F "file=@track.wav" \
  -o stems.zip
# → stems.zip contains harmonic.wav + percussive.wav

# Wider margin = harder separation (more aggressive)
curl -X POST http://localhost:8000/v1/audio/hpss \
  -F "file=@track.wav" \
  -F "margin=3.0" \
  -o stems.zip

# Output to staging
curl -X POST http://localhost:8000/v1/audio/hpss \
  -F "file=@track.wav" \
  -F "output_path=hpss/stems.zip"
```

Params: `margin` (default 1.0 — ≥1.0, higher = more aggressive), `kernel_size` (default 31 — odd int, median filter width), `output_format` (default `wav`).

### Spectral noise reduction

Stationary and non-stationary spectral noise reduction via noisereduce. No GPU, no model weights — pure spectral subtraction + Wiener filtering.

```bash
# Non-stationary mode (adaptive, default — good for variable background noise)
curl -X POST http://localhost:8000/v1/audio/noise-reduce \
  -F "file=@recording.wav" \
  -o clean.wav

# Stationary mode — targets constant hum, hiss, fan noise
curl -X POST http://localhost:8000/v1/audio/noise-reduce \
  -F "file=@recording.wav" \
  -F "stationary=true" \
  -o clean.wav

# Partial reduction — subtle noise floor cleanup
curl -X POST http://localhost:8000/v1/audio/noise-reduce \
  -F "file=@recording.wav" \
  -F "prop_decrease=0.5" \
  -o clean.wav
```

Params: `stationary` (bool, default `false`), `prop_decrease` (0–1, default 1.0 = full reduction), `output_format`, `output_path`, `output_url`.

For AI-based de-noise (higher quality, GPU-accelerated), use `/v1/audio/denoise/uvr-denoise` instead.

### Time-stretch and pitch-shift

Independent tempo factor and semitone offset via librosa phase vocoder. Slow a track down to learn it; shift a vocal up 3 semitones for a different key; transpose a MIDI melody to a different register first, then render.

```bash
# Slow down to 80% speed, no pitch change
curl -X POST http://localhost:8000/v1/audio/stretch \
  -F "file=@track.wav" \
  -F "tempo_factor=0.8" \
  -o slow.wav

# Shift up 3 semitones, no tempo change
curl -X POST http://localhost:8000/v1/audio/stretch \
  -F "file=@vocal.wav" \
  -F "pitch_semitones=3" \
  -o pitched.wav

# Both — pitch-corrected time stretch (traditional chipmunk effect)
curl -X POST http://localhost:8000/v1/audio/stretch \
  -F "file=@track.wav" \
  -F "tempo_factor=0.5" \
  -F "pitch_semitones=6" \
  -F "output_format=mp3" \
  -o stretched.mp3
```

Params: `tempo_factor` (default 1.0 — 0.5 = half speed), `pitch_semitones` (default 0.0 — ±semitones), `output_format`, `output_path`.

### Pitch correct

Auto-tune audio toward the nearest chromatic semitone using librosa's phase vocoder. Full `strength=1.0` snaps hard to pitch; lower values blend the corrected and original signal.

```bash
# Hard auto-tune — snap every note to the nearest semitone
curl -X POST http://localhost:8000/v1/audio/pitch-correct \
  -F "file=@vocal.wav" \
  -o tuned.wav

# Subtle correction — 50% blend
curl -X POST http://localhost:8000/v1/audio/pitch-correct \
  -F "file=@vocal.wav" \
  -F "strength=0.5" \
  -F "output_format=mp3" \
  -o tuned.mp3

# Async for long files, staged output
curl -X POST http://localhost:8000/v1/audio/pitch-correct \
  -F "file_path=sessions/take1.wav" \
  -F "strength=1.0" \
  -F "async_job=true" \
  -F "output_path=sessions/take1_tuned.wav"
```

Params: `strength` (0.0–1.0, default 1.0), `output_format`, `output_path`, `async_job`, `webhook_url`. Requires `librosa-analyze` engine.

### Repair

Declip clipped peaks and/or remove power-line hum. Declipping uses cubic interpolation to reconstruct flattened waveform tops and bottoms. Dehumming applies a notch filter at `hum_freq` (and harmonics).

```bash
# Declip only (default)
curl -X POST http://localhost:8000/v1/audio/repair \
  -F "file=@overdriven.wav" \
  -o repaired.wav

# Remove 60 Hz hum (North American power grid)
curl -X POST http://localhost:8000/v1/audio/repair \
  -F "file=@recording.wav" \
  -F "declip=false" \
  -F "dehum=true" \
  -F "hum_freq=60.0" \
  -o clean.wav

# Both — declip a 50 Hz humming mic recording
curl -X POST http://localhost:8000/v1/audio/repair \
  -F "file=@problem_track.wav" \
  -F "declip=true" \
  -F "dehum=true" \
  -F "hum_freq=50.0" \
  -F "output_format=flac" \
  -o repaired.flac
```

Params: `declip` (bool, default `true`), `dehum` (bool, default `false`), `hum_freq` (Hz, default 50.0), `output_format`, `output_path`, `async_job`, `webhook_url`.

### Audio tagging

Top-K AudioSet class label classification via Audio Spectrogram Transformer (MIT/ast-finetuned-audioset-10-10-0.4593). Identifies what's in a recording — music, speech, specific instruments, environmental sounds, etc.

```bash
curl -X POST http://localhost:8000/v1/audio/tag \
  -F "file=@recording.wav"
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
  -F "file=@soundscape.wav" \
  -F "top_k=20"
```

Requires the HF model cache. First run downloads the weights to `/data/hf/`. Optional: `top_k` (default 10).

> Run the container once with `-e HF_HUB_OFFLINE=0` and send one request to pull the model down. Subsequent runs use the cache with `HF_HUB_OFFLINE=1`.

### Audio embeddings

512-dimensional L2-normalized audio embeddings via LAION CLAP (laion/larger_clap_music_and_speech). Useful for semantic audio search, similarity scoring, and clustering.

```bash
# Get the embedding vector
curl -X POST http://localhost:8000/v1/audio/embed \
  -F "file=@track.wav"
# → {"embedding": [0.032, -0.11, ...], "dim": 512, "norm": 1.0}

# Semantic similarity — how well does the audio match a text description?
curl -X POST http://localhost:8000/v1/audio/embed \
  -F "file=@track.wav" \
  -F "query_text=energetic rock guitar riff"
# → {"embedding": [...], "dim": 512, "norm": 1.0,
#    "query_text": "energetic rock guitar riff", "similarity": 0.73}
```

`similarity` is cosine similarity in [-1, 1]. Requires HF model cache — same first-run download caveat as audio tagging.

### Zero-shot classification

Given audio and a list of free-form text labels, return cosine similarity scores for each using the existing CLAP model. No extra model download — uses the same `clap-embed` engine. Works for genres, moods, instruments, sonic descriptors — anything CLAP understands.

```bash
# Genre detection
curl -X POST http://localhost:8000/v1/audio/classify \
  -F "file=@track.wav" \
  -F 'labels=["jazz", "hip-hop", "classical", "electronic", "rock"]'
# → {"results": [
#     {"label": "hip-hop", "score": 0.42},
#     {"label": "electronic", "score": 0.38},
#     ...
#   ]}

# Mood / energy
curl -X POST http://localhost:8000/v1/audio/classify \
  -F "file=@track.wav" \
  -F 'labels=["energetic", "calm", "melancholic", "aggressive", "uplifting"]'

# Speaker gender
curl -X POST http://localhost:8000/v1/audio/classify \
  -F "file=@interview.wav" \
  -F 'labels=["male voice", "female voice", "child voice", "multiple speakers"]'
```

Results are sorted by descending score. Scores are cosine similarities in [-1, 1] — higher = more similar. Requires `clap-embed` model cache.

### Audio info

Probe any audio file for metadata without loading it into memory for processing. Uses ffprobe — handles any format.

```bash
curl -X POST http://localhost:8000/v1/audio/info \
  -F "file=@track.wav"
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

# Works on staged files too
curl -X POST http://localhost:8000/v1/audio/info \
  -F "file_path=recordings/interview.mp3"
# → {"codec": "mp3", "bit_rate": 192000, ...}
```

### Trim

Cut a precise time range out of any audio file. Common use: extract a chorus, clip a sample, chop a stem at bar boundaries.

```bash
# Extract seconds 30–90 from a track
curl -X POST http://localhost:8000/v1/audio/trim \
  -F "file=@track.wav" \
  -F "start_sec=30.0" \
  -F "end_sec=90.0" \
  -o chorus.wav

# Clip a specific beat range, export as mp3
curl -X POST http://localhost:8000/v1/audio/trim \
  -F "file=@stem.wav" \
  -F "start_sec=0.0" \
  -F "end_sec=8.0" \
  -F "output_format=mp3" \
  -o loop.mp3

# From staged file, write to staging
curl -X POST http://localhost:8000/v1/audio/trim \
  -F "file_path=sessions/full.wav" \
  -F "start_sec=120.5" \
  -F "end_sec=180.0" \
  -F "output_path=clips/verse.wav"
```

`start_sec` defaults to 0. `end_sec` is required and must be greater than `start_sec`. Supports all standard `output_format` values.

### Mix

Combine multiple staged or URL-accessible tracks into one. Per-track `gain_db` lets you balance levels before mixing. Useful for bouncing separated stems back together at custom levels, layering synth parts, or combining click-track + music.

```bash
# Mix drums and bass at equal levels
curl -X POST http://localhost:8000/v1/audio/mix \
  -F 'tracks=[{"file_path":"stems/drums.wav"},{"file_path":"stems/bass.wav"}]' \
  -o rhythm.wav

# Stems at custom levels (drums -3 dB, bass 0 dB, vocals +2 dB)
curl -X POST http://localhost:8000/v1/audio/mix \
  -F 'tracks=[
    {"file_path":"stems/drums.wav","gain_db":-3},
    {"file_path":"stems/bass.wav","gain_db":0},
    {"file_path":"stems/vocals.wav","gain_db":2}
  ]' \
  -F "output_format=wav" \
  -o custom_mix.wav

# Write to staging
curl -X POST http://localhost:8000/v1/audio/mix \
  -F 'tracks=[{"file_path":"stems/harmonic.wav"},{"file_path":"stems/percussive.wav","gain_db":-6}]' \
  -F "output_path=mixed/recombined.wav"
```

`tracks` is a required JSON array. Each entry needs `file_path` or `file_url` and an optional `gain_db` (default 0.0). Requires at least 2 tracks. Shorter tracks are padded with silence to match the longest.

### Concat

Stitch N audio files together in order. Handles different sample rates and channel counts automatically (ffmpeg resamples on the fly).

```bash
curl -X POST http://localhost:8000/v1/audio/concat \
  -F 'files=[{"file_path":"intro.wav"},{"file_path":"verse.wav"},{"file_path":"outro.wav"}]' \
  -o full_track.wav

# output_format and staging also work
curl -X POST http://localhost:8000/v1/audio/concat \
  -F 'files=[{"file_path":"a.wav"},{"file_path":"b.wav"}]' \
  -F "output_format=mp3" \
  -F "output_path=concat/result.mp3"
```

`files` is a required JSON array of `{file_path?, file_url?}` objects. Requires at least 2 entries.

### Speed

Change playback speed without pitch shifting — useful for auditioning at half/double speed, or creating slow-motion effects. Uses ffmpeg `atempo` filter chained for extreme multipliers.

```bash
# Half speed
curl -X POST http://localhost:8000/v1/audio/speed \
  -F "file=@track.wav" -F "speed=0.5" -o slow.wav

# Double speed
curl -X POST http://localhost:8000/v1/audio/speed \
  -F "file=@track.wav" -F "speed=2.0" -o fast.wav

# 4× speed (chains two atempo=2.0 filters internally)
curl -X POST http://localhost:8000/v1/audio/speed \
  -F "file_path=track.wav" -F "speed=4.0" -F "output_format=mp3" -o fast.mp3
```

`speed` is required. Range: 0.1–10.0. Note: this changes duration but not pitch. For pitch-preserving tempo changes use `/v1/audio/stretch`.

### Convert

Re-encode audio to a different format, sample rate, or channel count in a single call.

```bash
# WAV → 16 kHz mono FLAC (for speech models)
curl -X POST http://localhost:8000/v1/audio/convert \
  -F "file=@recording.wav" \
  -F "output_format=flac" \
  -F "sample_rate=16000" \
  -F "channels=1" \
  -o prepared.flac

# Stereo → mono WAV
curl -X POST http://localhost:8000/v1/audio/convert \
  -F "file_path=stereo.wav" \
  -F "channels=1" \
  -o mono.wav

# Any format → Opus at 48 kHz
curl -X POST http://localhost:8000/v1/audio/convert \
  -F "file=@audio.mp3" \
  -F "output_format=opus" \
  -F "sample_rate=48000" \
  -o out.opus
```

`output_format` defaults to `wav`. `sample_rate` and `channels` are optional; if omitted, the source values are preserved.

### Similar

Compute cosine similarity between two audio files using CLAP embeddings. Returns a score in [-1, 1] — 1 = identical sound, 0 = unrelated, negative = acoustically opposite. Useful for duplicate detection, cover matching, or finding the closest sample in a library.

```bash
curl -X POST http://localhost:8000/v1/audio/similar \
  -F "file=@original.wav" \
  -F "reference_file=@remix.wav"
# → {"similarity": 0.847, "dim": 512}

# Using staged files
curl -X POST http://localhost:8000/v1/audio/similar \
  -F "file_path=stems/vocals.wav" \
  -F "reference_file_path=stems/vocals_ref.wav"
```

Primary file: `file` / `file_path` / `file_url`. Reference file: `reference_file` / `reference_file_path` / `reference_file_url`. Requires `clap-embed` engine.

### MIDI quantize

Snap all note timings in a MIDI file to the nearest rhythmic grid. Cleaner dedicated endpoint than `/v1/midi/transform`'s `quantize_grid_beats` param.

```bash
# Quantize to 16th notes (0.25 beats)
curl -X POST http://localhost:8000/v1/midi/quantize \
  -F "file=@sloppy.mid" \
  -F "grid_beats=0.25" \
  -o tight.mid

# 8th note grid
curl -X POST http://localhost:8000/v1/midi/quantize \
  -F "file_path=recorded.mid" \
  -F "grid_beats=0.5" \
  -F "output_path=midi/quantized.mid"
```

`grid_beats`: grid size in beats — `0.25` = 16th note, `0.5` = 8th, `1.0` = quarter note. Default: `0.25`.

### Fade

Apply fade-in, fade-out, or both. 13 curve shapes: `tri`, `qsin`, `esin`, `hsin`, `log`, `ipar`, `qua`, `cub`, `squ`, `cbr`, `par`, `exp`, `lin`.

```bash
# 2s fade-in
curl -X POST http://localhost:8000/v1/audio/fade \
  -F "file=@track.wav" -F "fade_in=2.0" -o faded.wav

# 3s fade-out with exponential curve
curl -X POST http://localhost:8000/v1/audio/fade \
  -F "file=@track.wav" -F "fade_out=3.0" -F "curve=exp" -o faded.wav

# Both — 1s in, 2s out
curl -X POST http://localhost:8000/v1/audio/fade \
  -F "file=@track.wav" -F "fade_in=1.0" -F "fade_out=2.0" -o faded.wav
```

At least one of `fade_in` / `fade_out` must be > 0.

### Reverse

Flip audio backwards via ffmpeg `areverse`.

```bash
curl -X POST http://localhost:8000/v1/audio/reverse \
  -F "file=@sample.wav" -o reversed.wav

curl -X POST http://localhost:8000/v1/audio/reverse \
  -F "file_path=stems/vocals.wav" -F "output_format=mp3" -o reversed.mp3
```

### Loop

Repeat audio N times. Uses ffmpeg `aloop` filter — no re-encoding overhead per iteration.

```bash
# Play 4 times total
curl -X POST http://localhost:8000/v1/audio/loop \
  -F "file=@beat.wav" -F "count=4" -o looped.wav

# 8-bar loop → 32 bars
curl -X POST http://localhost:8000/v1/audio/loop \
  -F "file_path=stems/drums.wav" -F "count=4" -F "output_path=loops/drums32.wav"
```

`count` must be ≥ 2 (total plays, not extra loops).

### BPM match

Detect the source BPM via librosa, then time-stretch to the target — no manual math.

```bash
# Stretch anything to 128 BPM
curl -X POST http://localhost:8000/v1/audio/bpm-match \
  -F "file=@loop.wav" -F "target_bpm=128" -o matched.wav

# Match tempo and also shift pitch
curl -X POST http://localhost:8000/v1/audio/bpm-match \
  -F "file=@loop.wav" \
  -F "target_bpm=140" \
  -F "pitch_semitones=2" \
  -o matched.wav
```

Response includes `X-Source-BPM`, `X-Target-BPM`, and `X-Tempo-Factor` headers (also in JSON when `output_path` is used). Requires both `librosa-analyze` and `stretch` engines.

### Stereo width

Widen or collapse the stereo image via M/S processing. `width=0.0` → mono, `1.0` → original, `>1.0` → wider. Works on mono input too (upmixes first).

```bash
# Widen to 1.5×
curl -X POST http://localhost:8000/v1/audio/stereo-width \
  -F "file=@mix.wav" -F "width=1.5" -o wide.wav

# Collapse to mono
curl -X POST http://localhost:8000/v1/audio/stereo-width \
  -F "file=@mix.wav" -F "width=0.0" -o mono.wav

# Subtle narrowing for mix bus
curl -X POST http://localhost:8000/v1/audio/stereo-width \
  -F "file_path=master/mix.wav" -F "width=0.8" -F "output_path=master/narrow.wav"
```

Range: `[0.0, 3.0]`.

### Split

Split a file into segments. Two modes: `equal` (N equal time parts) or `silence` (split on quiet gaps). Returns a ZIP of numbered files.

```bash
# Split into 4 equal parts
curl -X POST http://localhost:8000/v1/audio/split \
  -F "file=@track.wav" -F "mode=equal" -F "count=4" -o segments.zip

# Split a DJ mix on silence
curl -X POST http://localhost:8000/v1/audio/split \
  -F "file=@djmix.wav" \
  -F "mode=silence" \
  -F "threshold_db=-40" \
  -F "min_duration_sec=1.0" \
  -o tracks.zip

# Split to mp3
curl -X POST http://localhost:8000/v1/audio/split \
  -F "file=@album.flac" -F "mode=equal" -F "count=10" -F "output_format=mp3" -o parts.zip
```

`mode=equal` requires `count >= 2`. `mode=silence` uses `threshold_db` (default -30) and `min_duration_sec` (default 0.5); requires the `silence-detect` engine.

### Pan

Position audio in the stereo field. Works on mono and stereo input.

```bash
# Hard left
curl -X POST http://localhost:8000/v1/audio/pan \
  -F "file=@vocal.wav" -F "position=-1.0" -o left.wav

# Slight right (e.g. guitar in mix)
curl -X POST http://localhost:8000/v1/audio/pan \
  -F "file_path=stems/guitar.wav" -F "position=0.4" -o guitar_panned.wav

# Center (no-op but valid)
curl -X POST http://localhost:8000/v1/audio/pan \
  -F "file=@mono.wav" -F "position=0.0" -o stereo.wav
```

`position`: -1.0 = hard left, 0.0 = center, 1.0 = hard right.

### EQ

Parametric EQ via ffmpeg `equalizer` filter. Pass any number of bands — each with a center frequency, gain, and optional bandwidth.

```bash
# Low-cut + presence boost
curl -X POST http://localhost:8000/v1/audio/eq \
  -F "file=@vocal.wav" \
  -F 'bands=[{"freq":100,"gain_db":-6,"width_hz":80},{"freq":3000,"gain_db":3,"width_hz":500}]' \
  -o eq.wav

# Single band: cut 60 Hz hum
curl -X POST http://localhost:8000/v1/audio/eq \
  -F "file=@recording.wav" \
  -F 'bands=[{"freq":60,"gain_db":-20,"width_hz":30}]' \
  -o clean.wav
```

Each band: `freq` (Hz, required), `gain_db` (dB, required, range ±30), `width_hz` (optional, default 100).

### Key match

Detect the source key via CLAP chord analysis, then pitch-shift to a target key — one call instead of two.

```bash
# Shift everything to C major
curl -X POST http://localhost:8000/v1/audio/key-match \
  -F "file=@loop.wav" -F "target_key=C" -o matched.wav

# Match to F# (response includes source_key + semitones shifted)
curl -X POST http://localhost:8000/v1/audio/key-match \
  -F "file_path=stems/melody.wav" \
  -F "target_key=F#" \
  -F "output_path=matched/melody_fsharp.wav"
```

`target_key`: root note, e.g. `C`, `F#`, `Bb`, `D#`. Mode suffix (`major`/`minor`/`m`) is ignored — only the root matters for pitch. Requires `chord-detect` and `stretch` engines.

### Sidechain duck

Duck a primary track (music) whenever a trigger track (voice) is loud — the classic voiceover-over-music effect. Pure ffmpeg `sidechaincompress`, no model required.

```bash
curl -X POST http://localhost:8000/v1/audio/sidechain-duck \
  -F "file=@music.wav" \
  -F "trigger_file=@voice.wav" \
  -F "threshold_db=-20" \
  -F "ratio=4" \
  -F "attack_ms=10" \
  -F "release_ms=200" \
  -o ducked.wav

# Aggressive duck for podcast-style music bed
curl -X POST http://localhost:8000/v1/audio/sidechain-duck \
  -F "file_path=music/bed.wav" \
  -F "trigger_file_path=voice/narration.wav" \
  -F "threshold_db=-30" \
  -F "ratio=10" \
  -F "release_ms=400" \
  -o "output_path=final/mix.wav"
```

Primary track is compressed whenever the trigger exceeds `threshold_db`. `ratio` sets compression intensity. Files must be the same duration for best results; shorter trigger is padded with silence.

### Effects chain

Apply an ordered chain of pedalboard effects — full catalog, you pick the order and params. Different from `/v1/audio/master` (which runs preset mastering chains).

```bash
# Compress, then add reverb, then drop -3 dB
curl -X POST http://localhost:8000/v1/audio/fx \
  -F "file=@track.wav" \
  -F 'effects=[
    {"type":"Compressor","params":{"threshold_db":-18,"ratio":4.0}},
    {"type":"Reverb","params":{"room_size":0.5,"wet_level":0.3}},
    {"type":"Gain","params":{"gain_db":-3.0}}
  ]' \
  -o out.wav
```

Allowed effects: `Compressor`, `Limiter`, `NoiseGate`, `Gain`, `Clipping`, `Distortion`, `Bitcrush`, `Reverb`, `Chorus`, `Delay`, `Phaser`, `PitchShift`, `HighShelfFilter`, `LowShelfFilter`, `PeakFilter`, `HighpassFilter`, `LowpassFilter`, `LadderFilter`, `IIRFilter`, `GSMFullRateCompressor`, `MP3Compressor`, `Resample`, `Invert`, `Convolution`.

VST3 / AudioUnit / external plugins are NOT in the allowlist — they load arbitrary native code.

### Loop point

Find the best seamless loop boundary in an audio file — audiolla analyses the beat grid and returns the start and end positions where a loop will repeat without a click or gap.

```bash
# Find best loop boundary (default: minimum 4 bars)
curl -X POST http://localhost:8000/v1/audio/loop-point \
  -F "file=@beat.wav" | jq '{loop_start_sec, loop_end_sec, bars, score, tempo_bpm}'
# → {"loop_start_sec": 0.0, "loop_end_sec": 7.44, "bars": 4,
#    "score": 0.94, "tempo_bpm": 128.0, "candidates": [...]}

# Require at least 8 bars, return top 3 candidates
curl -X POST http://localhost:8000/v1/audio/loop-point \
  -F "file=@long_track.wav" \
  -F "min_loop_bars=8" \
  -F "num_candidates=3"
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
    ]
  }' \
  -o song.mid

# Stage the MIDI for later via query-string output_path
curl -X POST 'http://localhost:8000/v1/midi/compose?output_path=midi/song.mid' \
  -H 'Content-Type: application/json' \
  -d @spec.json
```

Spec fields: `tempo_bpm` (default 120), `time_signature` (default `[4,4]`), `key_signature` (optional, e.g. `"C"`, `"Am"`), `ticks_per_beat` (default 480), `tracks[].{name, program, channel, volume, pan, notes[].{pitch, start_beats, duration_beats, velocity}}`. Time is in beats. `program` is GM program 0-127. Channel 9 is the GM drum channel — pitches there map to the drum kit (36 = kick, 38 = snare, 42 = closed hi-hat, etc.).

### Inspect MIDI

```bash
# read the structure of any Standard MIDI File
curl -X POST http://localhost:8000/v1/midi/inspect \
  -F "file=@song.mid"
# → {type, ticks_per_beat, tempo_changes, time_signatures,
#    tracks[{name, note_on_count, channels, programs, length_beats}], ...}
```

### Transform MIDI

```bash
# transpose all non-drum tracks up an octave
curl -X POST http://localhost:8000/v1/midi/transform \
  -F "file=@song.mid" \
  -F "transpose_semitones=12" \
  -o transposed.mid

# override tempo to 140 BPM and save to staging
curl -X POST http://localhost:8000/v1/midi/transform \
  -F "file=@song.mid" \
  -F "tempo_bpm=140" \
  -F "output_path=midi/fast.mid"

# drop the drum track (channel 9)
curl -X POST http://localhost:8000/v1/midi/transform \
  -F "file=@song.mid" \
  -F "drop_channels=9" \
  -o no-drums.mid

# keep only channels 0 and 1 (comma-separated)
curl -X POST http://localhost:8000/v1/midi/transform \
  -F "file=@song.mid" \
  -F "keep_channels=0,1" \
  -o two-ch.mid

# quantize to 1/16th notes
curl -X POST http://localhost:8000/v1/midi/transform \
  -F "file=@song.mid" \
  -F "quantize_grid_beats=0.25" \
  -o quantized.mid
```

`transpose_semitones` ±48. `quantize_grid_beats` is in beats (0.25 = 1/16th at 4/4). `keep_channels` and `drop_channels` take comma-separated channel numbers (`0,1,2`); only one can be set per request.

### Render MIDI to audio

```bash
# Synthesise via the bundled FluidR3_GM SoundFont
curl -X POST http://localhost:8000/v1/midi/render \
  -F "file=@song.mid" \
  -F "output_format=wav" \
  -o song.wav

# Use your own SoundFont (must be staged first)
curl -X PUT http://localhost:8000/v1/files/sf/orchestral.sf2 --data-binary @my.sf2
curl -X POST http://localhost:8000/v1/midi/render \
  -F "file=@song.mid" \
  -F "soundfont_path=sf/orchestral.sf2" \
  -F "output_format=flac" \
  -o orch.flac
```

### Generate music from a spec

Compose + render in one call — spec in, WAV out.

```bash
curl -X POST 'http://localhost:8000/v1/midi/generate?output_format=wav' \
  -H 'Content-Type: application/json' \
  -d @spec.json \
  -o song.wav
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
    }
  }' \
  -o beat.mid

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
    }
  }' \
  -o groove.mid
```

Body fields: `tempo_bpm` (default 120), `steps` (steps per bar, default 16), `bars` (default 1), `swing` (0.0–0.5, default 0.0), `pattern` (object — keys are drum voice names, values are arrays of 0/1). Supported voices: `kick`, `snare`, `hihat`, `open_hihat`, `ride`, `crash`, `clap`, `tom_hi`, `tom_mid`, `tom_low`, `rim`, `cowbell`. Requires `midi-compose` engine.

### Chords to MIDI

Detect the chord progression from an audio file and convert each segment to a MIDI chord (root + 3rd + 5th). Useful for exporting a detected chord chart as playable MIDI, re-harmonising an arrangement, or seeding a DAW session.

```bash
# Audio → chord MIDI at the detected tempo
curl -X POST http://localhost:8000/v1/audio/chords-to-midi \
  -F "file=@track.wav" \
  -o chords.mid

# Override tempo, set velocity and octave
curl -X POST http://localhost:8000/v1/audio/chords-to-midi \
  -F "file=@song.wav" \
  -F "tempo_bpm=120" \
  -F "velocity=90" \
  -F "octave=3" \
  -o chords.mid

# Stage the output
curl -X POST http://localhost:8000/v1/audio/chords-to-midi \
  -F "file_path=sessions/song.wav" \
  -F "output_path=midi/song_chords.mid"
```

Optional params: `tempo_bpm` (default: detected from audio), `velocity` (1–127, default 80), `octave` (0–8, default 4), `output_path`. Requires `chord-detect` engine. Each chord segment becomes a MIDI chord event (root + major 3rd/minor 3rd + perfect 5th, duration = segment length).

### Audio metadata tags

Read and write ID3 (MP3), Vorbis (OGG/FLAC), and WAV/M4A tags via mutagen. Requires the `metadata` engine.

```bash
# Read tags
curl -X POST http://localhost:8000/v1/audio/metadata \
  -F "file=@track.mp3" | jq '{title, artist, bpm, key, duration_sec}'

# Write tags — returns updated tag set
curl -X POST http://localhost:8000/v1/audio/metadata \
  -F "file=@track.mp3" \
  -F 'tags={"title":"My Track","artist":"DJ Audiolla","bpm":"128","year":"2026"}'
```

### Clip detection

Detect digital clipping. No engine required — pure numpy arithmetic.

```bash
curl -X POST http://localhost:8000/v1/audio/clip-detect \
  -F "file=@loud_master.wav" | jq '{clipped, clip_count, clip_ratio, peak_db}'
# → {"clipped":true,"clip_count":4219,"clip_ratio":0.0048,"peak_db":0.0}
```

### Mid/Side encode and decode

Encode L/R stereo to Mid+Side or decode back. Useful for stereo width surgery without touching the pedalboard chain.

```bash
# Encode L/R → M/S
curl -X POST http://localhost:8000/v1/audio/mid-side \
  -F "file=@stereo.wav" \
  -F "mode=encode" \
  -o ms_encoded.wav

# Decode back to L/R
curl -X POST http://localhost:8000/v1/audio/mid-side \
  -F "file=@ms_encoded.wav" \
  -F "mode=decode" \
  -o restored.wav
```

### Beat slice

Detect beat positions with librosa and return a ZIP of numbered WAV/MP3 slices — one file per beat interval.

```bash
curl -X POST http://localhost:8000/v1/audio/beat-slice \
  -F "file=@loop.wav" \
  -F "output_format=wav" \
  -o slices.zip
# → slices.zip: beat_001.wav, beat_002.wav, beat_003.wav …

# With output_path: stages the ZIP and returns JSON
curl -X POST http://localhost:8000/v1/audio/beat-slice \
  -F "file=@loop.wav" \
  -F "output_path=beats/loop_slices.zip"
# → {"path":"beats/loop_slices.zip","beat_count":32,...}
```

### Convolution reverb

Apply an impulse response (IR) to audio via pedalboard's `Convolution`. Any WAV file can be used as the IR.

```bash
# Upload your IR first
curl -X PUT http://localhost:8000/v1/files/ir/plate.wav --data-binary @plate_reverb.wav

# Apply — wet_mix: 0.0=dry only, 1.0=wet only
curl -X POST http://localhost:8000/v1/audio/conv-reverb \
  -F "file=@dry_vocal.wav" \
  -F "ir_file_path=ir/plate.wav" \
  -F "wet_mix=0.25" \
  -F "output_format=wav" \
  -o reverbed.wav
```

### Transient shaper

Attack/sustain dual-compressor blending. Positive `attack_gain_db` makes drums punchier; negative `sustain_gain_db` cuts room tail.

```bash
# Punchy drums: boost attack, cut sustain
curl -X POST http://localhost:8000/v1/audio/transient \
  -F "file=@drums.wav" \
  -F "attack_gain_db=6" \
  -F "sustain_gain_db=-4" \
  -o punchy_drums.wav

# Soft attack (pad-like)
curl -X POST http://localhost:8000/v1/audio/transient \
  -F "file=@synth.wav" \
  -F "attack_gain_db=-6" \
  -F "sustain_gain_db=0" \
  -o softened.wav
```

### DJ prep

One call returns everything a DJ needs about a track. Requires `librosa-analyze` + `chord-detect`. LUFS is reported when a loudness engine is available.

```bash
curl -X POST http://localhost:8000/v1/audio/dj-prep \
  -F "file=@track.wav" | jq .
# → {"bpm":128.0,"key":"A minor","camelot":"8A","integrated_lufs":-9.4}
```

Camelot wheel positions let you quickly find harmonically compatible tracks for mixing.

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
# Submit async — returns 202-style JSON immediately
curl -X POST http://localhost:8000/v1/audio/separate \
  -F "file=@track.wav" \
  -F "engine=htdemucs" \
  -F "async_job=true" \
  -F "webhook_url=https://my-server.com/hooks/audio" \
  -F "output_path=stems/track-vocals.wav"
# → {"job_id":"abc123","status":"pending"}

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
  -F "file_path=mytrack.wav" \
  -F "features=bpm"

# Separate stems and write the result back to staging
curl -X POST http://localhost:8000/v1/audio/separate \
  -F "file_path=mytrack.wav" \
  -F "engine=htdemucs" \
  -F "stems=vocals" \
  -F "output_path=stems/mytrack-vocals.wav"
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
  -F "file_url=https://my-bucket.s3.amazonaws.com/in.wav" \
  -F "reference_url=https://my-bucket.s3.amazonaws.com/ref.wav" \
  -F "mode=reference" \
  -F "output_url=https://my-bucket.s3.amazonaws.com/out.wav?X-Amz-Signature=..."
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
| `ffmpeg-render` | Static PNG spectrogram/waveform + 8-mode animated MP4/WebM video via ffmpeg filters. Backs `/v1/audio/{spectrogram,waveform,visualize}`. |
| `audio-fingerprint` | Chromaprint acoustic fingerprint via `fpcalc`. Backs `/v1/audio/fingerprint`. |
| `uvr-dereverb` | BS-Roformer de-reverb — removes room reverb; `primary_stem=No Reverb`. |
| `uvr-deecho` | VR Architecture de-echo (normal) — removes echo. |
| `uvr-deecho-aggressive` | VR Architecture de-echo (aggressive) — hard echo removal. |
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
| `hpss` | Harmonic/percussive source separation via librosa HPSS median filter — returns harmonic + percussive stems as a ZIP. Backs `/v1/audio/hpss`. |
| `noise-reduce` | Spectral noise reduction via noisereduce — stationary (constant hum/hiss) and non-stationary (adaptive) modes, no GPU required. Backs `/v1/audio/noise-reduce`. |
| `metadata` | Read/write audio tags (ID3 for MP3, Vorbis for OGG/FLAC, INFO for WAV, MP4 for M4A) via mutagen. No ML weights. Backs `/v1/audio/metadata`. |

Each Demucs variant is its own checkpoint (hosted on `dl.fbaipublicfiles.com`). The entrypoint prefetches every enabled variant into `/data/torch_cache/` at startup so the first separation request doesn't sit there downloading.

`AUDIOLLA_ENABLED_ENGINES` — restrict which engines are available. `AUDIOLLA_PRELOAD` — load specific engines into memory at startup instead of waiting for the first request.

---

## Endpoints

Full wire contract: [`openapi.yaml`](openapi.yaml).

### Audio processing

Every endpoint accepts exactly one of `file` / `file_path` / `file_url`.
Audio-producing endpoints additionally accept optional `output_path` /
`output_url` — when either is set, the response is JSON instead of audio
bytes.

| Method | Path | Default returns |
|--------|------|-----------------|
| `POST` | `/v1/audio/separate` | audio bytes for one stem; ZIP when requesting multiple (or all) stems |
| `POST` | `/v1/audio/master` | audio bytes |
| `POST` | `/v1/audio/analyze` | JSON — BPM, key, LUFS, spectral features |
| `POST` | `/v1/audio/beats` | JSON — BPM + beat timestamps; optional click-track WAV |
| `POST` | `/v1/audio/onsets` | JSON — onset timestamps |
| `POST` | `/v1/audio/melody` | JSON — dominant melody contour; optional MIDI export |
| `POST` | `/v1/audio/segments` | JSON — structural segment labels (A, B, C…) |
| `POST` | `/v1/audio/silence` | JSON — silent/non-silent ranges; optional trimmed audio |
| `POST` | `/v1/audio/spectrogram` | PNG bytes |
| `POST` | `/v1/audio/waveform` | PNG bytes |
| `POST` | `/v1/audio/visualize` | MP4 bytes (default `container=mp4`); pass `container=webm` for WebM — 8 animation modes |
| `POST` | `/v1/audio/fingerprint` | JSON — Chromaprint fingerprint string |
| `POST` | `/v1/audio/dereverb/{engine}` | audio bytes — room reverb removed |
| `POST` | `/v1/audio/deecho/{engine}` | audio bytes — echo removed |
| `POST` | `/v1/audio/denoise/{engine}` | audio bytes — broadband noise removed |
| `POST` | `/v1/audio/to_midi/{engine}` | MIDI bytes (`audio/midi`) — polyphonic transcription |
| `POST` | `/v1/audio/enhance/{engine}` | audio bytes — neural speech/vocal enhancement |
| `POST` | `/v1/audio/chords` | JSON — detected key and chord progression |
| `POST` | `/v1/audio/vad` | JSON — speech/non-speech segments with timestamps and speech ratio |
| `POST` | `/v1/audio/diarize/{engine}` | JSON — per-speaker timestamped segments |
| `POST` | `/v1/audio/transform` | audio bytes |
| `POST` | `/v1/audio/loudness` | JSON — `{loudness_lufs}` (measure only, no audio) |
| `POST` | `/v1/audio/loudness-curve` | JSON — `{curve:[{time_sec,rms_db}],duration,sample_rate,points}`; `hop_length` param |
| `POST` | `/v1/audio/normalize` | audio bytes — requires `target_lufs`; header `X-Loudness-LUFS` carries pre-normalization level |
| `POST` | `/v1/audio/hpss` | ZIP containing `harmonic.<fmt>` + `percussive.<fmt>` |
| `POST` | `/v1/audio/noise-reduce` | audio bytes |
| `POST` | `/v1/audio/stretch` | audio bytes |
| `POST` | `/v1/audio/pitch-correct` | audio bytes — `strength` [0.0–1.0]; requires `librosa-analyze` |
| `POST` | `/v1/audio/repair` | audio bytes — `declip` bool, `dehum` bool, `hum_freq` Hz |
| `POST` | `/v1/audio/tag` | JSON — top-K AudioSet labels with confidence scores |
| `POST` | `/v1/audio/embed` | JSON — 512-dim embedding; with `query_text` also returns cosine similarity |
| `POST` | `/v1/audio/classify` | JSON — `{results: [{label, score}]}` sorted descending; requires `clap-embed` |
| `POST` | `/v1/audio/info` | JSON — duration, sample_rate, channels, codec, bit_depth, format |
| `POST` | `/v1/audio/trim` | audio bytes — `start_sec` + `end_sec` required |
| `POST` | `/v1/audio/mix` | audio bytes — `tracks` JSON array required (≥2 entries) |
| `POST` | `/v1/audio/concat` | audio bytes — `files` JSON array required (≥2 entries) |
| `POST` | `/v1/audio/speed` | audio bytes — `speed` float required (0.1–10.0) |
| `POST` | `/v1/audio/convert` | audio bytes — format/sample_rate/channels conversion |
| `POST` | `/v1/audio/similar` | JSON — `{similarity, dim}`; requires `clap-embed` |
| `POST` | `/v1/audio/fade` | audio bytes — `fade_in`/`fade_out` seconds, 13 `curve` options |
| `POST` | `/v1/audio/reverse` | audio bytes — flips playback direction |
| `POST` | `/v1/audio/loop` | audio bytes — `count` total plays (≥2) |
| `POST` | `/v1/audio/bpm-match` | audio bytes — `target_bpm` required; requires `librosa-analyze` + `stretch` |
| `POST` | `/v1/audio/stereo-width` | audio bytes — `width` [0.0–3.0]; M/S stereo processing |
| `POST` | `/v1/audio/split` | ZIP — `mode=equal` (requires `count`) or `mode=silence` |
| `POST` | `/v1/audio/pan` | audio bytes — `position` [-1.0–1.0] |
| `POST` | `/v1/audio/eq` | audio bytes — `bands` JSON array of `{freq, gain_db, width_hz}` |
| `POST` | `/v1/audio/key-match` | audio bytes — `target_key` required; requires `chord-detect` + `stretch` |
| `POST` | `/v1/audio/sidechain-duck` | audio bytes — primary + `trigger_file_*`; ffmpeg sidechaincompress |
| `POST` | `/v1/audio/fx` | audio bytes |
| `POST` | `/v1/audio/metadata` | JSON — tag fields (title, artist, bpm, key, duration, sample_rate…); writes tags when `tags` JSON is provided |
| `POST` | `/v1/audio/clip-detect` | JSON — clipped, clip_count, clip_ratio, peak_db, duration_sec |
| `POST` | `/v1/audio/mid-side` | audio bytes — `mode=encode` (L/R→M/S) or `mode=decode` (M/S→L/R) |
| `POST` | `/v1/audio/beat-slice` | ZIP of numbered beat slices — requires `librosa-analyze` |
| `POST` | `/v1/audio/conv-reverb` | audio bytes — `ir_file` / `ir_file_path` / `ir_file_url` required; `wet_mix` [0.0–1.0] |
| `POST` | `/v1/audio/transient` | audio bytes — `attack_gain_db` + `sustain_gain_db` |
| `POST` | `/v1/audio/dj-prep` | JSON — bpm, key, camelot, integrated_lufs; requires `librosa-analyze` + `chord-detect` |
| `POST` | `/v1/audio/loop-point` | JSON — `{loop_start_sec,loop_end_sec,bars,score,tempo_bpm,candidates}`; requires `librosa-analyze` |
| `POST` | `/v1/audio/chords-to-midi` | MIDI bytes — chord progression from audio; requires `chord-detect` |

### Batch

| Method | Path | |
|--------|------|-|
| `POST` | `/v1/batch` | JSON body: array of op objects `{op, file_path, output_path, …}`. Returns `{results:[…]}` — errors per-op, not a 4xx. Supported ops: `convert`, `normalize`, `trim`, `fade`, `reverse`, `speed`, `eq`. |

### Async jobs

Every audio endpoint accepts `async_job=true` (Form field). Adds `webhook_url` optional delivery.

| Method | Path | |
|--------|------|-|
| `GET` | `/v1/jobs` | list jobs; optional `?status=pending\|running\|completed\|failed\|cancelled` |
| `GET` | `/v1/jobs/{job_id}` | poll one job — returns status, result, duration_sec |
| `DELETE` | `/v1/jobs/{job_id}` | cancel running job or remove completed job |

### MIDI

| Method | Path | Default returns |
|--------|------|-----------------|
| `POST` | `/v1/midi/compose` | MIDI bytes (`audio/midi`) — body is `application/json` song spec |
| `POST` | `/v1/midi/inspect` | JSON — tempo, tracks, channels, note counts, time/key signatures |
| `POST` | `/v1/midi/transform` | MIDI bytes — transpose, quantize, tempo override, channel filter |
| `POST` | `/v1/midi/quantize` | MIDI bytes — `grid_beats` snaps all note timings to a rhythmic grid |
| `POST` | `/v1/midi/render` | audio bytes — input MIDI via `file` / `file_path` / `file_url` |
| `POST` | `/v1/midi/generate` | audio bytes — body is `application/json` song spec (compose + render in one) |
| `POST` | `/v1/midi/drum` | MIDI bytes — body is `application/json` step-sequencer spec; requires `midi-compose` |

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
| `GET` | `/v1/engines` | list configured engines |
| `GET` | `/v1/ps` | list engines in memory right now |
| `DELETE` | `/v1/ps/{engine}` | evict one engine |
| `POST` | `/v1/unload` | evict everything |

---

## MCP

audiolla exposes a [Model Context Protocol](https://modelcontextprotocol.io) server at `/v1/mcp`. Point any MCP-capable LLM agent at it and it gets the full audio processing surface as callable tools — separate stems, detect chords, transcribe to MIDI, diarize speakers, compose music from a JSON spec, read/write tags, submit async jobs — all over JSON-RPC without writing a line of integration code.

Audio over MCP is base64-encoded (JSON-RPC can't carry raw bytes). The workflow: `put_file` to stage a file, call whatever tools you need, `get_file` to pull results back. Use `list_jobs` / `get_job` / `cancel_job` to manage long-running async work.

**Endpoint:** `http://localhost:8000/v1/mcp`

**Tools:**

| Tool | What it does |
|------|--------------|
| `list_engines` | List configured engines and whether they're loaded |
| `separate` | Demucs stem separation — base64 stems back, or per-stem PUT via `output_urls` |
| `master` | Reference mastering (matchering) or preset chain (pedalboard) |
| `analyze` | BPM, key, LUFS, spectral features via librosa |
| `beats` | Beat grid — BPM + timestamps; optional click-track audio |
| `onsets` | Note onset timestamps |
| `melody` | Dominant melody contour in Hz; optional MIDI export |
| `segments` | Structural segmentation — recurring section labels (A, B, C…) |
| `silence` | Detect silent gaps; optional auto-trim (edges or all) |
| `spectrogram` | Static PNG spectrogram via ffmpeg |
| `waveform` | Static PNG waveform via ffmpeg |
| `visualize` | Animated MP4/WebM — spectrum, waves, CQT, freqs, volume, vectorscope, phasemeter, histogram |
| `fingerprint` | Chromaprint acoustic fingerprint (AcoustID-compatible) |
| `dereverb` | Remove room reverb via UVR BS-Roformer |
| `deecho` | Remove echo via UVR VR Architecture |
| `denoise` | Remove broadband background noise via UVR MelBand Roformer |
| `audio_to_midi` | Polyphonic audio-to-MIDI transcription via basic-pitch (ONNX) — returns MIDI base64 |
| `enhance` | Neural speech and vocal enhancement via DeepFilterNet DF3 |
| `chords` | Chord and key detection via librosa — key + per-segment chord labels |
| `vad` | Voice activity detection via silero-vad — speech/non-speech segments with timestamps |
| `diarize` | Speaker diarization via pyannote — per-speaker timestamped segments |
| `transform` | Sox DSP chain — gain, EQ, reverb, pitch, tempo, etc. |
| `loudness` | Measure integrated LUFS — returns JSON only |
| `loudness_curve` | RMS envelope over time — `{curve:[{time_sec,rms_db}],duration,sample_rate,points}` |
| `normalize` | Normalize audio to a target LUFS level — returns base64 audio |
| `hpss` | Harmonic/percussive separation — returns per-stem base64 audio |
| `noise_reduce` | Spectral noise reduction — stationary or adaptive mode |
| `stretch` | Time-stretch + pitch-shift via librosa phase vocoder |
| `pitch_correct` | Auto-tune toward nearest chromatic semitone — `strength` [0.0–1.0]; requires `librosa-analyze` |
| `repair_audio` | Declip + dehum — `declip` bool, `dehum` bool, `hum_freq` Hz |
| `tag` | Audio tagging via AST — top-K AudioSet labels with confidence scores |
| `embed` | 512-dim CLAP audio embedding; with `query_text` returns cosine similarity |
| `classify` | Zero-shot CLAP classification — cosine similarity against any list of text labels |
| `info` | Probe audio metadata — duration, sample_rate, channels, codec, bit_depth |
| `trim` | Cut audio to [start_sec, end_sec) — returns base64 audio |
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
| `split` | Split into equal parts or on silence — returns `{segments:[{name,audio_base64}]}` |
| `pan` | Pan in the stereo field — `position` [-1.0–1.0] |
| `eq` | Parametric EQ — `bands` list of `{freq, gain_db, width_hz}` |
| `key_match` | Detect key then pitch-shift to `target_key` — returns source_key + semitones |
| `sidechain_duck` | Duck primary track on trigger — `threshold_db`, `ratio`, `attack_ms`, `release_ms` |
| `fx` | Generic pedalboard effects chain — full catalog, your order and params |
| `midi_compose` | JSON song spec → MIDI bytes (base64 or staged) |
| `midi_inspect` | Read MIDI structure — tempo, tracks, channels, note counts |
| `midi_transform` | Transpose, quantize, tempo override, channel filter on an existing MIDI file |
| `midi_render` | MIDI → audio via fluidsynth + SoundFont |
| `midi_generate` | One-shot compose + render — spec in, audio out |
| `drum_pattern` | Step-sequencer JSON spec → GM drum MIDI; `pattern` object of voice arrays, `swing`, `steps`, `bars` |
| `chords_to_midi` | Chord progression detected from audio → MIDI file; `tempo_bpm`, `velocity`, `octave` params |
| `audio_metadata` | Read or write audio tags — pass `tags` dict to write, omit to read |
| `detect_clipping` | Report digital clipping — clipped, clip_count, clip_ratio, peak_db |
| `mid_side` | M/S encode (`mode=encode`) or decode (`mode=decode`) stereo audio |
| `slice_at_beats` | Slice audio at beat positions — returns `{zip_base64, beat_count}` |
| `convolution_reverb` | Apply IR reverb — `ir_file_path`/`ir_file_url` + `wet_mix` [0.0–1.0] |
| `transient_shaper` | Attack/sustain shaping — `attack_gain_db`, `sustain_gain_db` |
| `dj_prep` | BPM + key + Camelot wheel + LUFS in one call |
| `find_loop_point` | Find best seamless loop boundary — `{loop_start_sec,loop_end_sec,bars,score,tempo_bpm,candidates}` |
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
| Music generation | MusicGen is CC-BY-NC. Stable Audio Open needs a Stability AI commercial agreement. Nothing permissively licensed at production quality exists yet. |
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

Every `make pkg-*` bumps `[tool.uv] exclude-newer` to today's UTC midnight before touching anything — packages younger than the gate are refused. Everything runs inside the dev container. Host needs `docker`, `make`, `git`.

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
