---
title: "Editing, time and pitch"
description: "Trim, mix, concat, fade, loop, split and slice audio, change speed, tempo, pitch and key, write tags, and render spectrograms, waveforms and videos."
nav_order: 10
---

# Editing, time and pitch

These endpoints cut, join and reshape audio: trim a clip, mix or concatenate files, fade, reverse, loop, split into parts, change speed or pitch, match a tempo or a key, edit tags, and render a picture or a video of the sound. Most are plain ffmpeg and need no model.

Every endpoint takes a JSON body with `file_path` or `file_url` and writes the result to `output_path` or `output_url`, as described in [input and output](getting-started.md#input-and-output). Add `"async_job": true` to run in the background ([async jobs](jobs.md)). Audio output defaults to `wav`; `output_format` also takes `mp3`, `flac`, `opus`, `aac` and `pcm`. The successful response is JSON with `path` (or `url`) and `size`, plus the endpoint-specific fields listed below. Full request schemas are in the [REST API reference](api.md), and inputs are staged as shown in [files](files.md).

## Trim

`POST /v1/audio/trim` cuts the range `[start_sec, end_sec)` out of a file. Common uses: extract a chorus, clip a sample, chop a stem at bar boundaries.

```bash
# Extract seconds 30 to 90 from a track
curl -X POST http://localhost:8000/v1/audio/trim \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","start_sec":30.0,"end_sec":90.0,"output_path":"out/chorus.wav"}'
# -> {"path":"out/chorus.wav","size":...,"start_sec":30.0,"end_sec":90.0,"output_format":"wav"}

# Clip the first 8 seconds of a stem, export as mp3
curl -X POST http://localhost:8000/v1/audio/trim \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/stem.wav",
    "start_sec": 0.0,
    "end_sec": 8.0,
    "output_format": "mp3",
    "output_path": "out/loop.mp3"
  }'

# Drop the first 12.5 seconds, keep the rest
curl -X POST http://localhost:8000/v1/audio/trim \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"sessions/full.wav","start_sec":12.5,"output_path":"clips/rest.wav"}'
```

`start_sec` defaults to 0 and must not be negative. `end_sec` is optional: leave it out to trim to the end of the source. It must be greater than `start_sec`.

## Mix

`POST /v1/audio/mix` sums two or more tracks into one with ffmpeg `amix`. Pass `file_paths` (staged files) or `file_urls` (remote files), not both. Use it to bounce separated stems back together, layer parts, or put a click track under music.

```bash
# Mix drums and bass
curl -X POST http://localhost:8000/v1/audio/mix \
  -H 'Content-Type: application/json' \
  -d '{
    "file_paths": ["stems/drums.wav", "stems/bass.wav"],
    "output_path": "out/rhythm.wav"
  }'
# -> {"path":"out/rhythm.wav","size":...,"track_count":2,"output_format":"wav"}

# Three stems, mp3 out
curl -X POST http://localhost:8000/v1/audio/mix \
  -H 'Content-Type: application/json' \
  -d '{
    "file_paths": ["stems/drums.wav", "stems/bass.wav", "stems/vocals.wav"],
    "output_format": "mp3",
    "output_path": "out/full_mix.mp3"
  }'
```

At least two inputs are required. Every track goes in at unity gain: the endpoint has no per-track level control, and `amix` runs with normalization off, so the result is a plain sum that can clip when loud tracks overlap. To set levels, change each track first (a `Gain` effect in [`/v1/audio/fx`](mastering-and-effects.md#effects-chain-pedalboard) or a `gain` op in [`/v1/audio/transform`](mastering-and-effects.md#transform-sox)), or use `POST /v1/audio/remix`, which separates a track and bounces the stems back with per-stem gain ([separation and restoration](separation-and-restoration.md)). The output is as long as the longest input.

## Concat

`POST /v1/audio/concat` joins two or more files end to end, in the order given. Pass `file_paths` or `file_urls`.

```bash
curl -X POST http://localhost:8000/v1/audio/concat \
  -H 'Content-Type: application/json' \
  -d '{
    "file_paths": ["intro.wav", "verse.wav", "outro.wav"],
    "output_path": "out/full_track.wav"
  }'
# -> {"path":"out/full_track.wav","size":...,"file_count":3,"output_format":"wav"}

# mp3 out, different staging path
curl -X POST http://localhost:8000/v1/audio/concat \
  -H 'Content-Type: application/json' \
  -d '{
    "file_paths": ["a.wav", "b.wav"],
    "output_format": "mp3",
    "output_path": "concat/result.mp3"
  }'
```

At least two inputs are required. When an input fails to load, the error `detail` starts with `file <index>:`.

## Speed

`POST /v1/audio/speed` changes playback speed without shifting pitch, through ffmpeg's `atempo` filter. Use it to audition at half or double speed. One `atempo` stage covers 0.5 to 2.0, so values outside that range are built from several stages (4.0 runs two `atempo=2.0` stages).

```bash
# Half speed
curl -X POST http://localhost:8000/v1/audio/speed \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","speed":0.5,"output_path":"out/slow.wav"}'

# Double speed
curl -X POST http://localhost:8000/v1/audio/speed \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","speed":2.0,"output_path":"out/fast.wav"}'

# 4x speed
curl -X POST http://localhost:8000/v1/audio/speed \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","speed":4.0,"output_format":"mp3","output_path":"out/fast.mp3"}'
```

`speed` is required, from 0.1 to 10.0. It changes duration, not pitch. For independent control of tempo and pitch use [time-stretch](#time-stretch-and-pitch-shift).

## Convert

`POST /v1/audio/convert` re-encodes to another format, sample rate or channel count in one call.

```bash
# WAV to 16 kHz mono FLAC (for speech models)
curl -X POST http://localhost:8000/v1/audio/convert \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/recording.wav",
    "output_format": "flac",
    "sample_rate": 16000,
    "channels": 1,
    "output_path": "out/prepared.flac"
  }'

# Stereo to mono WAV
curl -X POST http://localhost:8000/v1/audio/convert \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stereo.wav","channels":1,"output_path":"out/mono.wav"}'

# Any format to Opus at 48 kHz
curl -X POST http://localhost:8000/v1/audio/convert \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/audio.mp3",
    "output_format": "opus",
    "sample_rate": 48000,
    "output_path": "out/out.opus"
  }'
```

`output_format` defaults to `wav`. `sample_rate` (above 0) and `channels` (1 or 2) are optional; leave them out to keep the source values. The response echoes `output_format`, `sample_rate` and `channels`.

## Fade

`POST /v1/audio/fade` applies a fade-in, a fade-out or both, with ffmpeg `afade`. `curve` picks the shape, one of 13: `tri` (the default), `qsin`, `esin`, `hsin`, `log`, `ipar`, `qua`, `cub`, `squ`, `cbr`, `par`, `exp`, `lin`.

```bash
# 2 s fade-in
curl -X POST http://localhost:8000/v1/audio/fade \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","fade_in":2.0,"output_path":"out/faded.wav"}'

# 3 s fade-out with an exponential curve
curl -X POST http://localhost:8000/v1/audio/fade \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","fade_out":3.0,"curve":"exp","output_path":"out/faded.wav"}'

# Both: 1 s in, 2 s out
curl -X POST http://localhost:8000/v1/audio/fade \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","fade_in":1.0,"fade_out":2.0,"output_path":"out/faded.wav"}'
```

`fade_in` and `fade_out` are seconds and default to 0. `fade_in_sec` and `fade_out_sec` are accepted as aliases and win when both spellings are set. At least one fade must be above 0.

## Reverse

`POST /v1/audio/reverse` plays the audio backwards, through ffmpeg `areverse`. No extra parameters.

```bash
curl -X POST http://localhost:8000/v1/audio/reverse \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/sample.wav","output_path":"out/reversed.wav"}'

curl -X POST http://localhost:8000/v1/audio/reverse \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stems/vocals.wav","output_format":"mp3","output_path":"out/reversed.mp3"}'
```

## Loop

`POST /v1/audio/loop` repeats the audio, using ffmpeg's `aloop` filter. `count` is the total number of plays, not the number of extra repeats.

```bash
# Play 4 times in total
curl -X POST http://localhost:8000/v1/audio/loop \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/beat.wav","count":4,"output_path":"out/looped.wav"}'
# -> {"path":"out/looped.wav","size":...,"count":4}

# 8-bar drum loop to 32 bars
curl -X POST http://localhost:8000/v1/audio/loop \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stems/drums.wav","count":4,"output_path":"loops/drums32.wav"}'
```

`count` defaults to 2 and must be 2 or more. To find a loop boundary that repeats cleanly first, see `POST /v1/audio/loop-point` in [analysis](analysis.md).

## Split

`POST /v1/audio/split` cuts a file into parts and returns them as one ZIP. `mode` is `equal` (the default, N parts of equal length) or `silence` (split on quiet gaps). ZIP members are named `segment_000.<format>`, `segment_001.<format>` and so on.

```bash
# Split into 4 equal parts
curl -X POST http://localhost:8000/v1/audio/split \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","mode":"equal","count":4,"output_path":"out/segments.zip"}'
# -> {"path":"out/segments.zip","size":...,"segments":4,"mode":"equal"}

# Split a DJ mix on silence
curl -X POST http://localhost:8000/v1/audio/split \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/djmix.wav",
    "mode": "silence",
    "threshold_db": -40,
    "min_duration_sec": 1.0,
    "output_path": "out/tracks.zip"
  }'

# Split to mp3
curl -X POST http://localhost:8000/v1/audio/split \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/album.flac",
    "mode": "equal",
    "count": 10,
    "output_format": "mp3",
    "output_path": "out/parts.zip"
  }'
```

`mode=equal` needs `count` of 2 or more. `mode=silence` uses `threshold_db` (default -30) and `min_duration_sec` (default 0.5), needs the `silence-detect` engine, and returns 400 when it finds no non-silent part. `output_format` sets the format of each segment inside the ZIP. The split runs before the request returns, even with `async_job`; only the final write is deferred.

## Beat slice

`POST /v1/audio/beat-slice` detects beats with librosa and returns a ZIP with one file per beat interval, named `beat_001.<format>`, `beat_002.<format>` and so on. Each slice runs from one beat to the next; the last one runs to the end of the file, and anything before the first beat is dropped. Engine: `librosa-analyze`.

```bash
curl -X POST http://localhost:8000/v1/audio/beat-slice \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/loop.wav","output_format":"wav","output_path":"out/slices.zip"}'
# -> {"path":"out/slices.zip","size":...,"output_format":"wav","beat_count":32}
curl -o slices.zip http://localhost:8000/v1/files/out/slices.zip
# slices.zip: beat_001.wav, beat_002.wav, beat_003.wav, ...
```

A file with no detectable beats returns 400.

## Audio thumbnail

`POST /v1/audio/thumbnail` extracts the busiest stretch of a file: the window of `duration_sec` with the highest summed onset strength. Use it for preview clips, podcast teasers or DJ cue points. It needs the `librosa-analyze` engine.

```bash
# Default 30-second thumbnail
curl -X POST http://localhost:8000/v1/audio/thumbnail \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/long_track.wav","output_path":"out/preview.wav"}'

# 10-second teaser
curl -X POST http://localhost:8000/v1/audio/thumbnail \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/podcast.wav",
    "duration_sec": 10,
    "output_format": "mp3",
    "output_path": "out/teaser.mp3"
  }'
# -> {"path":"out/teaser.mp3","size":...,"start_sec":47.3,"end_sec":57.3,"duration_sec":10.0}
```

`duration_sec` defaults to 30 and must be between 1 and 300. The response tells you where in the source the thumbnail came from (`start_sec`, `end_sec`, `duration_sec`). When `duration_sec` is as long as the file or longer, the whole file comes back.

## Time-stretch and pitch-shift

`POST /v1/audio/stretch` changes tempo and pitch independently with librosa's phase vocoder, channel by channel, so stereo stays stereo. Slow a track down to learn it, or move a vocal into another key. Engine: `stretch`.

```bash
# Slow down to 80% speed, no pitch change
curl -X POST http://localhost:8000/v1/audio/stretch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","tempo_factor":0.8,"output_path":"out/slow.wav"}'

# Shift up 3 semitones, no tempo change
curl -X POST http://localhost:8000/v1/audio/stretch \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal.wav","pitch_semitones":3,"output_path":"out/pitched.wav"}'

# Both: half speed and up 6 semitones
curl -X POST http://localhost:8000/v1/audio/stretch \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "tempo_factor": 0.5,
    "pitch_semitones": 6,
    "output_format": "mp3",
    "output_path": "out/stretched.mp3"
  }'
# -> {"path":"out/stretched.mp3","size":...,"tempo_factor":0.5,"pitch_semitones":6.0}
```

`tempo_factor` defaults to 1.0 (0.5 is half speed, 2.0 double). `pitch_semitones` defaults to 0.0 and can be negative.

## Pitch correct

`POST /v1/audio/pitch-correct` nudges audio toward the nearest semitone. It tracks pitch with pyin, takes the median of the voiced frames, and shifts the whole file by the distance from that median to the nearest semitone. This fixes a recording that is consistently sharp or flat; it is one global shift, not per-note auto-tune. `strength` blends the shifted and original signal: 1.0 (the default) is the full shift, 0.0 returns the input unchanged. It needs the `librosa-analyze` engine.

```bash
# Full correction
curl -X POST http://localhost:8000/v1/audio/pitch-correct \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal.wav","output_path":"out/tuned.wav"}'

# 50% blend
curl -X POST http://localhost:8000/v1/audio/pitch-correct \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/vocal.wav",
    "strength": 0.5,
    "output_format": "mp3",
    "output_path": "out/tuned.mp3"
  }'

# Async for long files
curl -X POST http://localhost:8000/v1/audio/pitch-correct \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "sessions/take1.wav",
    "strength": 1.0,
    "async_job": true,
    "output_path": "sessions/take1_tuned.wav"
  }'
```

`strength` must be between 0.0 and 1.0. The file is returned unchanged when fewer than four voiced frames are found or the offset is under 0.05 semitones.

## BPM match

`POST /v1/audio/bpm-match` detects the source tempo with librosa, then time-stretches to `target_bpm`. It needs both the `librosa-analyze` and `stretch` engines.

```bash
# Stretch anything to 128 BPM
curl -X POST http://localhost:8000/v1/audio/bpm-match \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/loop.wav","target_bpm":128,"output_path":"out/matched.wav"}'
# -> {"path":"out/matched.wav","size":...,"target_bpm":128.0,"pitch_semitones":0.0,"source_bpm":120.19,"tempo_factor":1.065}

# Match tempo and also shift pitch
curl -X POST http://localhost:8000/v1/audio/bpm-match \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/loop.wav",
    "target_bpm": 140,
    "pitch_semitones": 2,
    "output_path": "out/matched.wav"
  }'
```

`target_bpm` is required and must be above 0. `pitch_semitones` defaults to 0. A file with no detectable tempo returns 400.

## Key match

`POST /v1/audio/key-match` detects the source key with the `chord-detect` engine (librosa chroma), then pitch-shifts to `target_key` with the `stretch` engine. It takes the shorter way round, so the shift is between -5 and +6 semitones.

```bash
# Shift everything to C
curl -X POST http://localhost:8000/v1/audio/key-match \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/loop.wav","target_key":"C","output_path":"out/matched.wav"}'

# Match to F#
curl -X POST http://localhost:8000/v1/audio/key-match \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stems/melody.wav","target_key":"F#","output_path":"matched/melody_fsharp.wav"}'
# -> {"path":"matched/melody_fsharp.wav","size":...,"target_key":"F#","source_key":"D major","semitones":4}
```

`target_key` is required: a root note such as `C`, `F#`, `Bb` or `D#`, case-insensitive. A mode suffix (`major`, `minor`, `maj`, `min`, `m`) is accepted and ignored; only the root matters. An unknown root returns 400.

## Audio metadata tags

`POST /v1/audio/metadata` reads and writes tags with mutagen: ID3 frames for MP3, Vorbis-style keys for FLAC and OGG. Engine: `metadata`.

```bash
# Read tags
curl -X POST http://localhost:8000/v1/audio/metadata \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.mp3"}' | jq '{title, artist, bpm, key, duration_sec}'

# Write tags and save the tagged file
curl -X POST http://localhost:8000/v1/audio/metadata \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.mp3",
    "tags": "{\"title\":\"My Track\",\"artist\":\"Some Artist\",\"bpm\":\"128\",\"year\":\"2026\"}",
    "output_path": "out/tagged.mp3"
  }'
# -> {"path":"out/tagged.mp3","size":...,"tags":{...},"output_format":"mp3","persisted":true}
```

A read returns `title`, `artist`, `album`, `genre`, `year`, `comment`, `track_number`, `bpm`, `key`, `encoder`, `duration_sec`, `sample_rate`, `channels` and `raw_tags` (every tag in the file). Those first ten names are also the fields you can write.

`tags` is a JSON-encoded string, not a JSON object: the request schema types it as a string and the server parses it, so an object gets a 422. With `output_path` or `output_url` the tagged audio is saved there, without re-encoding, and the response has `persisted: true`. Without an output target the write happens in memory only, and the response is the updated tag set with `persisted: false`. Output is optional on this endpoint, so a read needs neither `output_path` nor `output_url`.

## Visualize (spectrogram, waveform, video)

Visual output splits by type: still PNG images under `/v1/audio/visualize/image/` and animated video under `/v1/audio/visualize/video/{mode}`. All of them use the `ffmpeg-render` engine.

```bash
# Static PNG spectrogram
curl -X POST http://localhost:8000/v1/audio/visualize/image/spectrogram \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","width":1280,"height":720,"output_path":"out/spec.png"}'
curl -o spec.png http://localhost:8000/v1/files/out/spec.png

# Static PNG waveform
curl -X POST http://localhost:8000/v1/audio/visualize/image/waveform \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","width":1280,"height":240,"output_path":"out/wave.png"}'
curl -o wave.png http://localhost:8000/v1/files/out/wave.png

# Animated MP4 spectrum analyser
curl -X POST http://localhost:8000/v1/audio/visualize/video/spectrum \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "width": 1280,
    "height": 720,
    "fps": 30,
    "container": "mp4",
    "output_path": "out/viz.mp4"
  }'
curl -o viz.mp4 http://localhost:8000/v1/files/out/viz.mp4
```

`/image/spectrogram` renders ffmpeg's `showspectrumpic` with a legend. Params: `width` and `height` (64 to 8192, default 1280x720), `color` (default `intensity`) and `scale` (default `log`); `color` and `scale` take the values of the ffmpeg filter's options of the same name.

`/image/waveform` renders `showwavespic`. Params: `width` and `height` (64 to 8192, default 1280x720) and `color` (default `lime`).

`/video/{mode}` renders a video with the audio track muxed in. The eight modes and the ffmpeg filter behind each:

| Mode | Filter | What you see |
| --- | --- | --- |
| `spectrum` | `showspectrum` | Scrolling spectrogram |
| `waves` | `showwaves` | Oscilloscope line |
| `cqt` | `showcqt` | Constant-Q transform |
| `freqs` | `showfreqs` | Bar-graph frequency analyzer |
| `volume` | `showvolume` | Level meter |
| `vectorscope` | `avectorscope` | Stereo X/Y (Lissajous) scope |
| `phasemeter` | `aphasemeter` | Stereo phase meter |
| `histogram` | `ahistogram` | Level histogram |

Params: `width` and `height` (64 to 3840, default 1280x720), `fps` (1 to 120, default 30) and `container` (`mp4`, the default, with H.264 and AAC, or `webm` with VP9 and Opus). An unknown mode or container returns 400. The response echoes `mode`, `container`, `width`, `height` and `fps`.

## Errors

A missing engine returns 404 with `"<name> engine not configured"`; trim, mix, concat, speed, convert, fade, reverse, loop and equal-mode split need no engine at all. An unsupported `output_format` returns 415, and a bad parameter value returns 400 with a `detail` that names it. Every engine used on this page ships in both the CPU and the CUDA image ([engines](engines.md)).
