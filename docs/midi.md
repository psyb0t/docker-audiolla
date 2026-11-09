---
title: "MIDI"
description: "Audio-to-MIDI with basic-pitch, JSON song specs to MIDI, drum step patterns, chord MIDI, inspect, transform, quantize, humanize and FluidSynth rendering."
nav_order: 12
---

# MIDI

audiolla reads, writes and renders Standard MIDI Files. Transcribe a recording to MIDI, compose a song from a JSON spec, build a drum pattern from step arrays, turn a detected chord progression into MIDI, edit an existing file, and render any of it back to audio through a SoundFont. No AI runs in the compose path: the spec is the music, written by hand, by a script, or by an LLM agent.

Most endpoints here follow the standard contract: a JSON body with `file_path` xor `file_url`, and `output_path` xor `output_url` for anything that produces a file (see [Getting started](getting-started.md#input-and-output)). Three endpoints differ, because their JSON body is the musical spec itself: `/v1/midi/compose`, `/v1/midi/generate` and `/v1/midi/drum` take the output destination as query parameters, and without one they return the raw MIDI or audio bytes in the response. Field-level schemas are in the [REST API reference](api.md).

Engines: `basic-pitch` for transcription, `chord-detect` for chords to MIDI, `midi-render` (FluidSynth) for rendering, and `midi-compose` for everything else. All of them ship in both the CPU and the CUDA image ([Engines](engines.md)). A missing engine is a 404.

Of the endpoints on this page, only `/v1/audio/to_midi/{engine}` runs as a background job when you pass `async_job: true` ([Async jobs and webhooks](jobs.md)). The others always run inline, so give them `output_path` or `output_url`.

## Audio-to-MIDI transcription

Polyphonic audio-to-MIDI via Spotify's basic-pitch (ONNX backend, no TensorFlow). Play guitar, hum a melody, record a piano riff, and get a MIDI file back with the notes.

```bash
# Any audio -> MIDI file (staged)
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/guitar_riff.wav","output_path":"out/riff.mid"}'
curl -o riff.mid http://localhost:8000/v1/files/out/riff.mid

# Tune the detection thresholds
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/piano.wav",
    "onset_threshold": 0.6,
    "frame_threshold": 0.3,
    "minimum_note_length_ms": 80,
    "output_path": "out/piano.mid"
  }'

# Write directly to a different staging path
curl -X POST http://localhost:8000/v1/audio/to_midi/basic-pitch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"recordings/bass.wav","output_path":"midi/bass_notes.mid"}'
# -> {"path":"midi/bass_notes.mid","size":...,"engine":"basic-pitch","output_format":"mid"}
```

Optional params: `onset_threshold` (default 0.5), `frame_threshold` (default 0.3), `minimum_note_length_ms` (default 58), `minimum_frequency` / `maximum_frequency` (Hz, unset means unconstrained), `multiple_pitch_bends` (default false), `melodia_trick` (default true, helps with melodic content). `basic-pitch` is the only transcription engine; any other slug in the path is a 404 (unknown) or a 400 (not a transcription engine). The engine unloads other loaded engines before it runs.

Feed the MIDI file to [`/v1/midi/inspect`](#inspect-midi) or [`/v1/midi/render`](#render-midi-to-audio) for a full audio to MIDI to audio round trip.

## Compose MIDI

POST a JSON song spec, get a Standard MIDI File back. Write the spec by hand, generate it from a tracker or sequencer, script it in a notebook, or have an LLM produce it.

```bash
# 4-beat C major arpeggio at 120 BPM, piano + kick drum
curl -X POST 'http://localhost:8000/v1/midi/compose?output_path=midi/song.mid' \
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
  }'
# -> {"path":"midi/song.mid","size":...,"engine":"midi-compose"}
curl -o song.mid http://localhost:8000/v1/files/midi/song.mid

# Use a JSON spec file and get the MIDI bytes straight back
curl -X POST http://localhost:8000/v1/midi/compose \
  -H 'Content-Type: application/json' \
  -d @spec.json \
  -o song.mid
```

The body is the spec and nothing else. Pass `output_path` or `output_url` as a query parameter to stage or upload the file and get JSON back; with neither, the response is the MIDI file itself (`audio/midi`, `composed.mid`). The endpoint also accepts multipart form data with the spec as JSON in a `spec` field and the destination in `output_path` / `output_url` fields.

Spec fields (the engine checks every one and answers 400 with the offending path, for example `tracks[0].notes[3].pitch must be in [0, 127], got 130`):

| Field | Default | Valid values |
| --- | --- | --- |
| `tempo_bpm` | `120` | 1 to 999 |
| `time_signature` | `[4, 4]` | `[numerator, denominator]`, numerator 1 to 32, denominator 1, 2, 4, 8, 16 or 32 |
| `key_signature` | none | a key like `"C"`, `"Am"`, `"F#"`, `"Bbm"` |
| `ticks_per_beat` | `480` | 24 to 1920 |
| `tracks` | required | non-empty list of track objects |
| `tracks[].name` | none | any string |
| `tracks[].program` | `0` | GM program 0 to 127 |
| `tracks[].channel` | `0` | 0 to 15; channel 9 is the GM drum channel |
| `tracks[].volume` | `100` | 0 to 127 (CC 7) |
| `tracks[].pan` | `64` | 0 to 127 (CC 10) |
| `tracks[].notes` | required | list of note objects (may be empty) |
| `notes[].pitch` | required | 0 to 127 (60 is middle C) |
| `notes[].start_beats` | `0.0` | 0 or more |
| `notes[].duration_beats` | required | at least 1/64 of a beat |
| `notes[].velocity` | `100` | 1 to 127 |

Time is in beats. On channel 9, pitches map to the GM drum kit (36 kick, 38 snare, 42 closed hi-hat, and so on).

## Inspect MIDI

Read the structure of any Standard MIDI File as JSON.

```bash
curl -X POST http://localhost:8000/v1/midi/inspect \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid"}'
# -> {"type":1,"ticks_per_beat":480,"length_seconds":2.0,
#     "tempo_changes":[{"tick":0,"bpm":120.0}],
#     "time_signatures":[{"tick":0,"numerator":4,"denominator":4}],
#     "key_signatures":[],
#     "tracks":[{"index":1,"name":"Lead","length_ticks":960,"length_beats":2.0,
#                "note_on_count":4,"note_off_count":4,"channels":[0],"programs":[0]},...],
#     "track_count":3,"size_bytes":...}
```

An empty or unparseable file is a 400.

## Transform MIDI

Transpose, quantize, re-tempo or filter channels in an existing MIDI file.

```bash
# transpose all non-drum tracks up an octave
curl -X POST http://localhost:8000/v1/midi/transform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","transpose_semitones":12,"output_path":"midi/transposed.mid"}'

# override tempo to 140 BPM and save to staging
curl -X POST http://localhost:8000/v1/midi/transform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","tempo_bpm":140,"output_path":"midi/fast.mid"}'

# drop the drum channel (9)
curl -X POST http://localhost:8000/v1/midi/transform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","drop_channels":"9","output_path":"midi/no-drums.mid"}'

# keep only channels 0 and 1
curl -X POST http://localhost:8000/v1/midi/transform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","keep_channels":"0,1","output_path":"midi/two-ch.mid"}'

# quantize to 1/16th notes
curl -X POST http://localhost:8000/v1/midi/transform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/song.mid","quantize_grid_beats":0.25,"output_path":"midi/quantized.mid"}'
```

`transpose_semitones` is -48 to 48 (default 0). It never touches channel 9, and a note pushed outside 0 to 127 is dropped. `quantize_grid_beats` is in beats (0.25 is a 16th note in 4/4) and must be above 0; it snaps note starts and keeps durations. `tempo_bpm` (1 to 999) replaces every tempo event. `keep_channels` and `drop_channels` are comma-separated channel numbers in a string (`"0,1"`), and only one of them can be set per request. The response adds `engine`, `transpose_semitones`, `quantize_grid_beats` and `tempo_bpm` to the usual `path` / `url` and `size`.

## MIDI quantize

Snap note starts to a rhythmic grid. This is a shorter way to call the transform above with only `quantize_grid_beats`.

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

`grid_beats` is the grid size in beats: `0.25` is a 16th note, `0.5` an 8th, `1.0` a quarter. Default `0.25`; 0 or below is a 400.

## MIDI humanize

Add small timing and velocity variations so a programmed part sounds less mechanical. The jitter is uniformly distributed and, when you pass a `seed`, the same input gives the same output every time.

```bash
# Gentle humanize with defaults (up to 10 ms timing, up to 10% velocity)
curl -X POST http://localhost:8000/v1/midi/humanize \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/rigid.mid","output_path":"midi/human.mid"}'

# Heavier feel with a fixed seed for reproducible results
curl -X POST http://localhost:8000/v1/midi/humanize \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "midi/drums.mid",
    "timing_ms": 20,
    "velocity_pct": 15,
    "seed": 42,
    "output_path": "midi/drums_human.mid"
  }'

# Stage output under a different path
curl -X POST http://localhost:8000/v1/midi/humanize \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"midi/pattern.mid","timing_ms":8,"output_path":"midi/pattern_human.mid"}'
# -> {"path":"midi/pattern_human.mid","size":...,"timing_ms":8.0,"velocity_pct":10.0}
```

Optional params: `timing_ms` (maximum shift either way, 0 to 500, default 10), `velocity_pct` (maximum change either way as a percentage of 127, 0 to 50, default 10), `seed` (any integer). Input that is not a MIDI file is a 400. This endpoint reads its input from `file_path` only; `file_url` is rejected with a 400.

## Render MIDI to audio

Synthesize a MIDI file through FluidSynth and a SoundFont. Engine: `midi-render`.

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
  -d '{
    "file_path": "midi/song.mid",
    "soundfont_path": "sf/orchestral.sf2",
    "output_format": "flac",
    "output_path": "out/orch.flac"
  }'
```

Both images ship FluidR3_GM and point `AUDIOLLA_SOUNDFONT` at it ([Configuration](configuration.md)). `soundfont_path` is a path in the staging area, checked like any `file_path`; a missing file is a 400. Other params: `gain` (0.0 to 5.0, default 0.5), `samplerate` (22050, 44100, 48000, 88200 or 96000; default 44100) and `output_format` (`wav`, `mp3`, `flac`, `opus`, `aac` or `pcm`; default `wav`). Input without a MIDI header is a 400.

## Generate music from a spec

Compose and render in one call: the same song spec as [Compose MIDI](#compose-midi) goes in, audio comes out. It needs both `midi-compose` and `midi-render`.

```bash
# Stage the rendered audio
curl -X POST 'http://localhost:8000/v1/midi/generate?output_path=out/song.wav' \
  -H 'Content-Type: application/json' \
  -d @spec.json
# -> {"path":"out/song.wav","size":...,"engine":"midi-generate","output_format":"wav","midi_size":...}
curl -o song.wav http://localhost:8000/v1/files/out/song.wav

# FLAC through a staged SoundFont, bytes straight back
curl -X POST 'http://localhost:8000/v1/midi/generate?output_format=flac&soundfont_path=sf/orchestral.sf2' \
  -H 'Content-Type: application/json' \
  -d @spec.json \
  -o song.flac
```

As with compose, the body is only the spec. `output_path`, `output_url`, `output_format` (default `wav`), `soundfont_path`, `gain` (default 0.5) and `samplerate` (default 44100) are query parameters, with the same ranges as render. An unsupported `output_format` is a 415. Without `output_path` or `output_url` the response is the audio file itself. Multipart form data with a `spec` field also works, with the other knobs as form fields.

## Drum pattern

Step sequencer spec in, GM drum MIDI out. Each drum voice is an array of steps; the server maps the voices to channel 9 pitches and writes a MIDI file. Swing delays every second step for a shuffled feel.

```bash
# 4-on-the-floor kick, snare on 2 and 4, busy hi-hat: 2 bars at 120 BPM
curl -X POST 'http://localhost:8000/v1/midi/drum?output_path=midi/beat.mid' \
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
  }'
# -> {"path":"midi/beat.mid","size":...}
curl -o beat.mid http://localhost:8000/v1/files/midi/beat.mid

# Swing groove: 0.1 = subtle, 0.5 = strong shuffle
curl -X POST 'http://localhost:8000/v1/midi/drum?output_path=midi/groove.mid' \
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
  }'
```

Like compose, the body is the pattern spec and the destination goes in the `output_path` or `output_url` query parameter; without one the MIDI bytes come back directly.

Body fields: `tempo_bpm` (1 to 999, default 120), `steps` (steps per 4/4 bar, 1 to 64, default 16), `bars` (1 to 64, default 1, the pattern repeats every bar), `swing` (0.0 to 0.5, default 0.0) and `pattern` (required, non-empty object of voice name to step array). A step of `0` is a rest and `1` is a hit at velocity 100; an integer from 2 to 127 is a hit at that velocity.

Voice names: `kick`, `snare`, `hihat`, `hihat_closed`, `hihat_open`, `ride`, `crash`, `tom_high`, `tom_mid`, `tom_low`, `clap`, `rim`, `cowbell`, `tambourine`, `shaker`, `wood_block`. A key that is a number from 0 to 127 is used as the MIDI note directly. Any other key is a 400 that lists the supported names.

## Chords to MIDI

Detect the chord progression of an audio file and write each chord segment as a held MIDI chord (root, third and fifth). Use it to export a chord chart as playable MIDI or to seed a DAW session. Engine: `chord-detect`.

```bash
# Audio -> chord MIDI at 120 BPM
curl -X POST http://localhost:8000/v1/audio/chords-to-midi \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","output_path":"out/chords.mid"}'
# -> {"path":"out/chords.mid","size":...,"chord_count":42,"key":"A minor","tempo_bpm":120.0}

# Set tempo, velocity and octave
curl -X POST http://localhost:8000/v1/audio/chords-to-midi \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/song.wav",
    "tempo_bpm": 120,
    "velocity": 90,
    "octave": 3,
    "output_path": "out/chords.mid"
  }'

# Stage the output under a different path
curl -X POST http://localhost:8000/v1/audio/chords-to-midi \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"sessions/song.wav","output_path":"midi/song_chords.mid"}'
```

Optional params: `tempo_bpm` (1 to 999, default 120; the tempo is not detected from the audio), `velocity` (1 to 127, default 80), `octave` (1 to 7, default 4). Each segment from [chord detection](analysis.md#chord-and-key-detection) becomes one chord: root, major or minor third, and perfect fifth, held for the segment's length. Audio with no detected chords is a 400.
