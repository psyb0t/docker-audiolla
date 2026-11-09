---
title: "Analysis"
description: "Measure audio over HTTP: BPM, key, LUFS, beats, onsets, melody, chords, silence, fingerprints, CLAP embeddings, AudioSet tags and stereo field."
nav_order: 8
---

# Analysis

These endpoints measure a file and answer with JSON. Use them to find the tempo and key of a track, check loudness before mastering, locate silence, tag what is in a recording, or compare two clips. Most of them write no audio, so they need no `output_path` or `output_url`. The few that can also produce a file (a click track, a melody MIDI file, trimmed audio) say so below.

Every request is a JSON body with exactly one of `file_path` (a file staged under `/v1/files`) or `file_url` (a remote URL, off by default). The full input and output contract is in [Getting started](getting-started.md#input-and-output), staging and remote URLs are in [Files and remote URLs](files.md), and every field of every request is in the [REST API reference](api.md).

Each endpoint below names the engine it needs. When that engine is missing (for example because `AUDIOLLA_ENABLED_ENGINES` left it out), the endpoint answers 404 with `"<engine> engine not configured"`. All engines on this page ship in both the CPU and the CUDA image; see [Engines](engines.md).

The examples assume a staged input:

```bash
curl -X PUT --data-binary @track.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/track.wav
```

## Analyze

One call for the basic numbers. Engine: `librosa-analyze`.

```bash
# returns JSON. features: bpm, key, loudness, duration,
# spectral_centroid, rms, zcr. Omit features to get them all.
curl -X POST http://localhost:8000/v1/audio/analyze \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","features":["bpm","key","loudness"]}'
# -> {"bpm":123.05,"key":"F# minor","loudness_lufs":-9.8,"duration":215.3,...}
```

The response keys are `bpm`, `key` (for example `"C major"`, `"A minor"`), `loudness_lufs`, `duration`, `spectral_centroid`, `rms` and `zcr`. `duration` is always filled; a feature you did not ask for comes back as `null`, and so does a feature whose computation failed. An unknown name in `features` is a 400 that lists the valid ones.

## Beats, onsets, melody, segments

All four use the `librosa-analyze` engine.

```bash
# beat grid: tempo + beat timestamps
curl -X POST http://localhost:8000/v1/audio/beats \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# -> {"tempo_bpm":128.0,"beats":[0.48,0.95,...],"beat_count":412,"duration":215.3}

# onset timestamps: note attacks, transients
curl -X POST http://localhost:8000/v1/audio/onsets \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# -> {"onsets":[{"time":0.12,"strength":0.83},...],"count":981,"duration":215.3}

# dominant melody contour: pitch in Hz per frame
curl -X POST http://localhost:8000/v1/audio/melody \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# -> {"fmin":65.0,"fmax":2093.0,"frame_seconds":0.023,"contour":[{"time":0.0,"hz":null,"voiced":false},...],"duration":215.3}

# structural segmentation: labels recurring sections A, B, C...
curl -X POST http://localhost:8000/v1/audio/segments \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","num_segments":6}'
# -> {"segments":[{"start_sec":0.0,"end_sec":31.2,"label":"A","cluster_id":0},...],"tempo_bpm":128.0,"duration":215.3}
```

Beats: pass `start_bpm` (for example `140`) to seed the tracker when you already know the rough tempo. With `click_track=true` the server also renders the input mixed with a metronome click on every beat, which is handy for checking the grid by ear. Set `output_path` or `output_url` to receive that audio as a file (the beat data moves into the same JSON response); without either, the click track comes back inline as base64 in `click_track_base64`. `output_format` picks the click-track format (default `wav`).

Melody: `fmin` and `fmax` bound the pitch search in Hz (defaults `65.0` and `2093.0`). With `as_midi=true` the contour is also quantized to notes and written as a single-track MIDI file at 120 BPM; the response adds `midi_notes`. Set `output_path` or `output_url` to get the `.mid` file, otherwise it comes back as base64 in `midi_base64`. Re-tempo it afterwards with [`/v1/midi/transform`](midi.md#transform-midi).

Segments: `num_segments` must be between 2 and 32 (default 6). Short or featureless input that does not give enough beats comes back as one `A` segment covering the whole file.

Beats, melody and silence accept `async_job` when they write a file; see [Async jobs and webhooks](jobs.md).

## Silence detection and trimming

Engine: `silence-detect` (ffmpeg `silencedetect`).

```bash
# find silent gaps in a recording (no trim_mode: JSON only)
curl -X POST http://localhost:8000/v1/audio/silence \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","threshold_db":-30,"min_duration_sec":1.0}'

# trim all silence and stage the result
curl -X POST http://localhost:8000/v1/audio/silence \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "threshold_db": -30,
    "min_duration_sec": 0.5,
    "trim_mode": "all",
    "output_path": "out/trimmed.wav"
  }'
curl -o trimmed.wav http://localhost:8000/v1/files/out/trimmed.wav

# trim only leading/trailing silence
curl -X POST http://localhost:8000/v1/audio/silence \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "threshold_db": -40,
    "min_duration_sec": 0.3,
    "trim_mode": "edges",
    "output_path": "processed/trimmed.wav"
  }'
```

`threshold_db` (default `-30`) must be 0 or below; `min_duration_sec` (default `0.5`) must be above 0. `trim_mode=edges` chops leading and trailing silence only. `trim_mode=all` removes every detected gap (compress a talk recording, tighten a loop). Any other `trim_mode` is a 400, and so is trimming a file that is silent from start to end.

Without `trim_mode` the response is JSON only: `silent_ranges` (each with `start_sec`, `end_sec`, `duration_sec`), `non_silent_ranges`, `duration`, `threshold_db` and `min_duration_sec`, and `output_path` / `output_url` is not needed. With `trim_mode` set, give `output_path` or `output_url` to get the trimmed file; without either, the trimmed audio comes back as base64 in `trimmed_audio_base64`.

## Acoustic fingerprint

Engine: `audio-fingerprint` (Chromaprint `fpcalc`).

```bash
# Chromaprint fingerprint: identifies a recording regardless of encoding
curl -X POST http://localhost:8000/v1/audio/fingerprint \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# -> {"duration": 215.34, "fingerprint": "AQADtEqRRIuQ..."}

# include the raw integer array (for custom similarity scoring)
curl -X POST http://localhost:8000/v1/audio/fingerprint \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","return_raw":true}'
# -> {"duration": 215.34, "fingerprint": "AQADtEqRRIuQ...", "fingerprint_raw": [12, 35, ...]}
```

`analyze_seconds` (default `120`) caps how much audio `fpcalc` reads; `0` reads the whole file, a negative value is a 400. The base64 fingerprint string is the format the [AcoustID](https://acoustid.org) lookup service takes.

## Chord and key detection

Krumhansl-Schmuckler key estimation plus chroma-template chord segmentation via librosa. Engine: `chord-detect`.

```bash
curl -X POST http://localhost:8000/v1/audio/chords \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# -> {
#      "key": "C major",
#      "key_confidence": 0.87,
#      "duration": 183.4,
#      "chords": [
#        {"chord": "C major", "start_sec": 0.0, "end_sec": 2.3, "confidence": 0.91},
#        {"chord": "A minor", "start_sec": 2.3, "end_sec": 4.6, "confidence": 0.85},
#        ...
#      ]
#    }

# Tune the hop length (lower = finer time resolution)
curl -X POST http://localhost:8000/v1/audio/chords \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","hop_length":256}'
```

Chords are major and minor triads, named like the key (`"F# major"`, `"D minor"`). Optional params: `hop_length` (default 512), `segment_min_duration_sec` (default 0.5, merges very short chord segments). To turn the detected progression into MIDI, use [chords to MIDI](midi.md#chords-to-midi).

## Loudness measurement

Integrated loudness (ITU-R BS.1770 via pyloudnorm). Engine: `librosa-analyze`. To change the level instead of measuring it, use `/v1/audio/normalize` ([Mastering, dynamics and effects](mastering-and-effects.md)).

```bash
# Measure integrated LUFS: returns JSON, no audio output
curl -X POST http://localhost:8000/v1/audio/loudness \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# -> {"loudness_lufs": -18.4, "target_lufs": null, "normalized": false}
```

## Loudness curve

RMS envelope over time, as a list of `{time_sec, rms_db}` points. Use it for gain automation curves, finding loud and quiet sections, or looking at dynamic range before mastering. No engine needed.

```bash
# Default hop (512 samples): fine-grained envelope
curl -X POST http://localhost:8000/v1/audio/loudness/curve \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}' | jq '.curve[:5]'
# -> [
#      {"time_sec": 0.0,   "rms_db": -18.4},
#      {"time_sec": 0.012, "rms_db": -17.9},
#      ...
#    ]

# Coarser envelope (2048-sample hop)
curl -X POST http://localhost:8000/v1/audio/loudness/curve \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","hop_length":2048}' | jq '{duration, sample_rate, points}'
```

Response fields: `curve` (array of `{time_sec, rms_db}`), `duration` (seconds), `sample_rate`, `hop_length` and `points` (curve length). `hop_length` defaults to 512 and must be between 64 and 8192.

## Audio tagging

Top-K AudioSet labels from the Audio Spectrogram Transformer (`MIT/ast-finetuned-audioset-10-10-0.4593`). It tells you what is in a recording: music, speech, instruments, environmental sounds. Engine: `ast-tag`.

```bash
curl -X POST http://localhost:8000/v1/audio/tag \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/recording.wav"}'
# -> {
#      "tags": [
#        {"label": "Music", "score": 0.94},
#        {"label": "Drum", "score": 0.87},
#        {"label": "Guitar", "score": 0.71},
#        ...
#      ],
#      "duration": 5.2
#    }

# Get top 20 results instead of the default 10
curl -X POST http://localhost:8000/v1/audio/tag \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/soundscape.wav","top_k":20}'
```

Optional: `top_k` (default 10). The weights download from Hugging Face on the first call and are cached under `/data/hf/` (`HF_HOME`).

The images default to `HF_HUB_OFFLINE=0`, so the first call downloads the weights. For a deployment with no egress, download the model into the mounted `/data/hf` volume beforehand (for example with `huggingface-cli download <model>`), then start the container with `-e HF_HUB_OFFLINE=1`. See [Configuration](configuration.md).

## Audio embeddings

512-dimensional, L2-normalized audio embeddings from LAION CLAP (`laion/larger_clap_music_and_speech`). Use them for semantic audio search, similarity scoring and clustering. Engine: `clap-embed`.

```bash
# Get the embedding vector
curl -X POST http://localhost:8000/v1/audio/embed \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# -> {"embedding": [0.032, -0.11, ...], "dim": 512}

# Semantic similarity: how well does the audio match a text description?
curl -X POST http://localhost:8000/v1/audio/embed \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","query_text":"energetic rock guitar riff"}'
# -> {"embedding": [...], "dim": 512,
#     "similarity": 0.73, "query_text": "energetic rock guitar riff"}
```

`similarity` is the cosine similarity between the audio and the text, in [-1, 1]. Same first-run download as audio tagging.

## Zero-shot classification

Give it audio and a list of free-form text labels, and it scores each label with the CLAP model. It uses the same `clap-embed` engine, so there is no extra download. It works for genres, moods, instruments, voice types, anything CLAP understands.

```bash
# Genre detection
curl -X POST http://localhost:8000/v1/audio/classify \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","labels":["jazz","hip-hop","classical","electronic","rock"]}'
# -> {"results": [
#      {"label": "hip-hop", "score": 0.42},
#      {"label": "electronic", "score": 0.38},
#      ...
#    ]}

# Mood / energy
curl -X POST http://localhost:8000/v1/audio/classify \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","labels":["energetic","calm","melancholic","aggressive","uplifting"]}'

# Speaker gender
curl -X POST http://localhost:8000/v1/audio/classify \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/interview.wav","labels":["male voice","female voice","child voice","multiple speakers"]}'
```

`labels` is required and must be a non-empty array of strings. Results are sorted by descending score. Scores are cosine similarities in [-1, 1], higher is closer.

## Audio info

Probe a file for its format metadata with ffprobe. No engine needed, and any format ffprobe reads works.

```bash
curl -X POST http://localhost:8000/v1/audio/info \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}'
# -> {
#      "size_bytes": 52428800,
#      "duration_sec": 297.241,
#      "sample_rate": 44100,
#      "channels": 2,
#      "codec": "pcm_s16le",
#      "sample_fmt": "s16",
#      "format": "wav",
#      "bit_depth": 16,
#      "bit_rate": 1411200
#    }

# Works on any staged file
curl -X POST http://localhost:8000/v1/audio/info \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"recordings/interview.mp3"}'
# -> {"codec": "mp3", "bit_rate": 192000, ...}
```

`bit_depth`, `bit_rate` and `frames` appear only when ffprobe reports them. A file with no audio stream is a 400.

## Similar

Cosine similarity between two audio files, from their CLAP embeddings. The score is in [-1, 1]: 1 is the same sound, around 0 is unrelated. Use it for duplicate detection, cover matching, or finding the closest sample in a library. Engine: `clap-embed`.

```bash
curl -X POST http://localhost:8000/v1/audio/similar \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/original.wav","reference_file_path":"uploads/remix.wav"}'
# -> {"similarity": 0.847, "dim": 512}

# Different staged paths
curl -X POST http://localhost:8000/v1/audio/similar \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stems/vocals.wav","reference_file_path":"stems/vocals_ref.wav"}'
```

Primary file: `file_path` or `file_url`. Reference file: `reference_file_path` or `reference_file_url` (also accepted as `file_path_b` and `file_url_b`).

## Loop point

Find the loop boundary in a file that repeats with the least audible seam. The engine snaps candidates to the beat grid, compares the sound at each candidate start and end (MFCC similarity), and returns the closest match. Engine: `librosa-analyze`.

```bash
# Find best loop boundary (default: minimum 4 bars)
curl -X POST http://localhost:8000/v1/audio/loop-point \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/beat.wav"}' | jq '{loop_start_sec, loop_end_sec, bars, score, tempo_bpm}'
# -> {"loop_start_sec": 0.0, "loop_end_sec": 7.44, "bars": 4,
#     "score": 0.94, "tempo_bpm": 128.0}

# Require at least 8 bars, return top 3 candidates
curl -X POST http://localhost:8000/v1/audio/loop-point \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/long_track.wav","min_loop_bars":8,"num_candidates":3}'
```

Response fields: `loop_start_sec`, `loop_end_sec`, `bars`, `score` (higher is a tighter loop), `tempo_bpm`, `duration` and `candidates` (ranked alternatives, each with `start_sec`, `end_sec`, `bars`, `score`). Optional params: `min_loop_bars` (1 to 64, default 4) and `num_candidates` (1 to 20, default 5). When the file has too few beats for the requested length, the response carries `bars: 0`, an empty `candidates` list and a `note` explaining why.

## Clip detection

Detect digital clipping. No engine needed; it is plain numpy arithmetic.

```bash
curl -X POST http://localhost:8000/v1/audio/clip-detect \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/loud_master.wav"}' | jq '{clipped, clip_count, clip_ratio, peak_db}'
# -> {"clipped":true,"clip_count":4219,"clip_ratio":0.0048,"peak_db":0.0}
```

The full response also has `duration_sec`, `sample_rate` and `channels`. To fix clipped audio, see `/v1/audio/repair` in [Separation and restoration](separation-and-restoration.md).

## DJ prep

One call returns the numbers a DJ wants about a track: BPM, key, its Camelot wheel position and integrated LUFS. It needs both `librosa-analyze` and `chord-detect` (404 if either is missing).

```bash
curl -X POST http://localhost:8000/v1/audio/dj-prep \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav"}' | jq .
# -> {"bpm":128.0,"key":"A minor","camelot":"8A","integrated_lufs":-9.4}
```

Camelot positions let you find harmonically compatible tracks for mixing. `camelot` is an empty string when the key is not one of the 24 major and minor keys, and `integrated_lufs` is `null` when the loudness measurement fails.

## Stereo field analysis

Measure stereo width, phase correlation, left/right balance and mono compatibility. No engine needed.

```bash
curl -X POST http://localhost:8000/v1/audio/stereo-field \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/stereo_mix.wav"}' | jq .
# -> {
#      "correlation": 0.72,
#      "width": 0.41,
#      "balance_db": -0.3,
#      "mono_compatible": true,
#      "mid_level_db": -12.1,
#      "side_level_db": -18.4,
#      "phase_issues": false,
#      "channels": 2,
#      "sample_rate": 44100,
#      "duration": 210.5
#    }

# Analyze a different staged file
curl -X POST http://localhost:8000/v1/audio/stereo-field \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"masters/track.wav"}' | jq '{correlation, width, mono_compatible}'
```

`correlation` is the Pearson correlation between left and right, in [-1, 1]. `width` is side RMS over mid RMS. `balance_db` is the level difference between left and right. `mono_compatible` is true when correlation is 0.5 or higher, and `phase_issues` is true when correlation is below 0, a red flag for phase-cancelled material that collapses on mono playback. Mono files return `correlation=1.0`, `width=0.0`, `mono_compatible=true` and `channels=1`.
