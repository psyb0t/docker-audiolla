---
title: "Mastering, dynamics and effects"
description: "Reference and preset mastering, LUFS normalization, pedalboard and SoX chains, multiband compression, de-essing, ducking, EQ, pan and stereo width."
nav_order: 7
---

# Mastering, dynamics and effects

These endpoints change how a track sounds without changing what is in it: mastering against a reference, loudness normalization, effect chains, compression, EQ and stereo placement. Use them on a finished mix, on a stem before you bounce it, or as steps in a [pipeline](workflows.md).

Every endpoint here takes a JSON body with `file_path` or `file_url` and writes audio to `output_path` or `output_url`, as described in [input and output](getting-started.md#input-and-output). Add `"async_job": true` to run in the background ([async jobs](jobs.md)). Output defaults to `wav`; `output_format` also takes `mp3`, `flac`, `opus`, `aac` and `pcm`. The successful response is JSON with `path` (or `url`) and `size`, plus the endpoint-specific fields listed below. Full request schemas are in the [REST API reference](api.md).

Stage inputs first with `PUT /v1/files/{path}` ([files](files.md)):

```bash
curl -X PUT --data-binary @track.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/track.wav
```

## Master

`POST /v1/audio/master` runs in one of two modes:

- `reference`: matches the EQ and loudness of your track to a reference track with matchering (engine `matchering`). Pass `reference_path` or `reference_url`.
- `chain`: runs a built-in pedalboard mastering chain (engine `pedalboard-chain`). Pass `preset`, either `transparent` or `loud`.

`mode` is optional. A request with `reference_path` or `reference_url` runs `reference`, one with `preset` runs `chain`, and one with neither gets a 400.

```bash
# stage track + reference
curl -X PUT --data-binary @track.wav -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/track.wav
curl -X PUT --data-binary @ref.wav -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/uploads/ref.wav

# match EQ + loudness to a reference track
curl -X POST http://localhost:8000/v1/audio/master \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "mode": "reference",
    "reference_path": "uploads/ref.wav",
    "output_path": "out/mastered.wav"
  }'
curl -o mastered.wav http://localhost:8000/v1/files/out/mastered.wav

# run a built-in pedalboard chain (presets: transparent, loud)
curl -X POST http://localhost:8000/v1/audio/master \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "mode": "chain",
    "preset": "loud",
    "output_path": "out/mastered.wav"
  }'
# -> {"path":"out/mastered.wav","size":...,"engine":"pedalboard-chain","mode":"chain","output_format":"wav"}
```

What the two chain presets do (`src/audiolla/engines/pedalboard_chain.py`):

| Preset | Chain | Default loudness target |
| --- | --- | --- |
| `transparent` | Compressor (-18 dB, 2:1), high shelf +1.5 dB at 8 kHz, +2 dB gain, limiter at -1 dB | -14 LUFS |
| `loud` | Compressor (-24 dB, 4:1), high shelf +2.5 dB at 9 kHz, +4 dB gain, limiter at -0.3 dB | -8 LUFS |

`target_lufs` overrides the preset's loudness target. In `reference` mode the output is normalized to `target_lufs` only when you pass it. Values outside `-70.0` to `-0.1` get a 400. These chain presets are not the multi-step workflow presets at `GET /v1/presets`; those are covered in [presets, pipelines and batch](workflows.md).

matchering and pedalboard are GPL v3. That is fine for self-hosted use; distributing the image as a product needs a GPL compliance review.

## Loudness normalization

`POST /v1/audio/normalize` measures integrated loudness with pyloudnorm and applies gain to hit `target_lufs`. Engine: `librosa-analyze`.

```bash
# Normalize to -14 LUFS (streaming platform standard)
curl -X POST http://localhost:8000/v1/audio/normalize \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","target_lufs":-14,"output_path":"out/normalized.wav"}'
# -> {"path":"out/normalized.wav","size":...,"target_lufs":-14.0,"output_format":"wav","measured_lufs":-18.4}
curl -o normalized.wav http://localhost:8000/v1/files/out/normalized.wav

# EBU R128 broadcast level, written to a different staging path
curl -X POST http://localhost:8000/v1/audio/normalize \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/track.wav","target_lufs":-23,"output_path":"mastered/norm.wav"}'
```

`target_lufs` is required and must be between `-70.0` and `-0.1`. The response carries `measured_lufs`, the level before normalization. To measure without writing audio, use `POST /v1/audio/loudness` ([analysis](analysis.md)).

## Transform (SoX)

`POST /v1/audio/transform` runs a SoX effect chain through pysox. Engine: `sox-transform`. `operations` is a required array of `{op, params}` objects, applied in order:

| `op` | `params` |
| --- | --- |
| `gain` | `db` (required) |
| `equalizer` | `frequency`, `gain_db` (required), `width_q` (default 1.0) |
| `compand` | `attack_time` (0.02), `decay_time` (0.2), `soft_knee_db` (6.0), `tf_points` (list of `[in_db, out_db]`) |
| `reverb` | `reverberance` 0 to 100 (50), `pre_delay_ms` (0), `room_scale` (100) |
| `pitch` | `n_semitones` (required, semitones, not cents) |
| `tempo` | `factor` (required) |
| `rate` | `samplerate` (required) |
| `channels` | `n_channels` (required) |
| `trim` | `start_time` (required), `end_time` |
| `pad` | `start_duration` (0), `end_duration` (0) |

An unknown `op` or a missing required param is a 400.

```bash
# pitch shift up 2 semitones + add reverb, export mp3
curl -X POST http://localhost:8000/v1/audio/transform \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "operations": [
      {"op": "pitch", "params": {"n_semitones": 2}},
      {"op": "reverb", "params": {"reverberance": 50}}
    ],
    "output_format": "mp3",
    "output_path": "out/out.mp3"
  }'
curl -o out.mp3 http://localhost:8000/v1/files/out/out.mp3
```

## Effects chain (pedalboard)

`POST /v1/audio/fx` applies an ordered chain of pedalboard effects, with your order and your params. Engine: `fx-chain`. It is different from `/v1/audio/master`, which only runs the two fixed mastering chains.

`effects` is a required array of `{type, params}` objects. `params` go to the pedalboard class constructor as keyword arguments, so the names are pedalboard's own (for example `threshold_db`, `ratio`, `room_size`, `wet_level`, `cutoff_frequency_hz`). A wrong param name or an out-of-range value is a 400 that quotes pedalboard's error.

```bash
# Compress, then add reverb, then drop 3 dB
curl -X POST http://localhost:8000/v1/audio/fx \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/track.wav",
    "effects": [
      {"type": "Compressor", "params": {"threshold_db": -18, "ratio": 4.0}},
      {"type": "Reverb", "params": {"room_size": 0.5, "wet_level": 0.3}},
      {"type": "Gain", "params": {"gain_db": -3.0}}
    ],
    "output_path": "out/out.wav"
  }'
```

Allowed `type` values (`_ALLOWED_EFFECTS` in [`src/audiolla/engines/fx_chain.py`](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/engines/fx_chain.py)): `Compressor`, `Limiter`, `NoiseGate`, `Gain`, `Clipping`, `Distortion`, `Bitcrush`, `Reverb`, `Chorus`, `Delay`, `Phaser`, `PitchShift`, `HighShelfFilter`, `LowShelfFilter`, `PeakFilter`, `HighpassFilter`, `LowpassFilter`, `LadderFilter`, `IIRFilter`, `GSMFullRateCompressor`, `MP3Compressor`, `Resample`, `Invert`, `Convolution`.

VST3, AudioUnit and other external plugins are not in the allowlist, because they load arbitrary native code. Mono input is duplicated to two channels before the chain runs, and the output is clipped to full scale and written as 16-bit PCM before encoding.

## Multiband compression

`POST /v1/audio/multiband-compress` splits the signal into N+1 frequency bands, compresses each band on its own, and sums them back. The split uses zero-phase Butterworth filters run forward and backward (LR4-equivalent), so a chain with no compression reconstructs the original. Use it to tame bass thump without squashing vocal sibilance, or to level out a busy mid-range.

```bash
# 3-band mastering pass: low/mid/high
curl -X POST http://localhost:8000/v1/audio/multiband-compress \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/mixdown.wav",
    "crossovers_hz": [200, 3000],
    "bands": [
      {"threshold_db": -18, "ratio": 4, "attack_ms": 15, "release_ms": 150, "makeup_db": 1.5},
      {"threshold_db": -14, "ratio": 3, "attack_ms": 8, "release_ms": 80, "makeup_db": 1.0},
      {"threshold_db": -10, "ratio": 2, "attack_ms": 3, "release_ms": 40, "makeup_db": 0.5}
    ],
    "output_path": "out/mastered.wav"
  }'
```

`crossovers_hz` and `bands` are required. With N crossovers you pass N+1 bands. Each crossover must be above 0 Hz and below the file's Nyquist frequency. Each band needs `threshold_db` and `ratio`; `attack_ms` (default 10), `release_ms` (default 100) and `makeup_db` (default 0) are optional. The response echoes `crossovers_hz` and `bands`.

## Transient shaper

`POST /v1/audio/transient` shapes attack and sustain separately. Positive `attack_gain_db` makes drums punchier; negative `sustain_gain_db` cuts the room tail. Both default to 0.

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

## De-ess

`POST /v1/audio/deess` is a split-band de-esser. A Butterworth high-pass isolates the band above `frequency_hz`, an envelope follower tracks it, and the band is compressed per channel when it crosses `threshold_db`. The rest of the signal is untouched. No engine required.

```bash
# Default settings (threshold -20 dB, 6 kHz, 4:1 ratio)
curl -X POST http://localhost:8000/v1/audio/deess \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal.wav","output_path":"out/deessed.wav"}'

# Gentle pass on a mix
curl -X POST http://localhost:8000/v1/audio/deess \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/mix.wav",
    "threshold_db": -15,
    "frequency_hz": 7000,
    "ratio": 2.5,
    "output_path": "out/mix_deessed.wav"
  }'
# -> {"path":"out/mix_deessed.wav","size":...,"threshold_db":-15.0,"frequency_hz":7000.0,"ratio":2.5}
```

Optional params: `threshold_db` (dBFS, default -20), `frequency_hz` (1000 to 16000, default 6000), `ratio` (1.0 to 50.0, default 4.0). Values outside those ranges get a 400.

## Sidechain duck

`POST /v1/audio/sidechain-duck` lowers a primary track (music) whenever a trigger track (voice) is loud: the voiceover-over-music effect. It is ffmpeg's `sidechaincompress` filter, no model involved. Pass the trigger as `trigger_file_path` or `trigger_file_url`.

```bash
# stage music + voice first via PUT /v1/files/...
curl -X POST http://localhost:8000/v1/audio/sidechain-duck \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/music.wav",
    "trigger_file_path": "uploads/voice.wav",
    "threshold_db": -20,
    "ratio": 4,
    "attack_ms": 10,
    "release_ms": 200,
    "output_path": "out/ducked.wav"
  }'

# Aggressive duck for podcast-style music bed
curl -X POST http://localhost:8000/v1/audio/sidechain-duck \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "music/bed.wav",
    "trigger_file_path": "voice/narration.wav",
    "threshold_db": -30,
    "ratio": 10,
    "release_ms": 400,
    "output_path": "final/mix.wav"
  }'
```

The primary track is compressed whenever the trigger exceeds `threshold_db` (must be 0 or below, default -20). `ratio` (at least 1.0, default 4) sets how hard. `attack_ms` (default 10) and `release_ms` (default 200) must be above 0. The output contains only the processed primary track; the trigger is used for detection and is not mixed in.

## Convolution reverb

`POST /v1/audio/conv-reverb` applies an impulse response (IR) with pedalboard's `Convolution`. Any audio file ffmpeg can decode works as the IR. Pass it as `ir_file_path` or `ir_file_url`.

```bash
# Upload your IR first
curl -X PUT --data-binary @plate_reverb.wav \
  -H 'Content-Type: application/octet-stream' \
  http://localhost:8000/v1/files/ir/plate.wav

# Apply: wet_mix 0.0 = dry only, 1.0 = wet only
curl -X POST http://localhost:8000/v1/audio/conv-reverb \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/dry_vocal.wav",
    "ir_file_path": "ir/plate.wav",
    "wet_mix": 0.25,
    "output_path": "out/reverbed.wav"
  }'
```

`wet_mix` defaults to 0.3 and must be between 0.0 and 1.0.

## EQ

`POST /v1/audio/eq` is a parametric EQ built on ffmpeg's `equalizer` filter. Pass any number of bands, each with a center frequency, a gain and an optional bandwidth.

```bash
# Low-cut + presence boost
curl -X POST http://localhost:8000/v1/audio/eq \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/vocal.wav",
    "bands": [
      {"freq": 100, "gain_db": -6, "width_hz": 80},
      {"freq": 3000, "gain_db": 3, "width_hz": 500}
    ],
    "output_path": "out/eq.wav"
  }'

# Single band: cut 60 Hz hum
curl -X POST http://localhost:8000/v1/audio/eq \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/recording.wav",
    "bands": [{"freq": 60, "gain_db": -20, "width_hz": 30}],
    "output_path": "out/clean.wav"
  }'
# -> {"path":"out/clean.wav","size":...,"band_count":1}
```

`bands` is required and needs at least one entry. Each band: `freq` (Hz, above 0, required), `gain_db` (required, -30 to 30), `width_hz` (above 0, default 100). For a dedicated hum remover see `POST /v1/audio/repair` in [separation and restoration](separation-and-restoration.md).

## Pan

`POST /v1/audio/pan` places audio in the stereo field. `position` runs from -1.0 (hard left) through 0.0 (center, the default) to 1.0 (hard right). Mono input comes out as stereo.

```bash
# Hard left
curl -X POST http://localhost:8000/v1/audio/pan \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal.wav","position":-1.0,"output_path":"out/left.wav"}'

# Slight right (a guitar in the mix)
curl -X POST http://localhost:8000/v1/audio/pan \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"stems/guitar.wav","position":0.4,"output_path":"out/guitar_panned.wav"}'

# Center: turns a mono file into centered stereo
curl -X POST http://localhost:8000/v1/audio/pan \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/mono.wav","position":0.0,"output_path":"out/stereo.wav"}'
```

## Stereo width

`POST /v1/audio/stereo-width` widens or collapses the stereo image with mid/side processing. `width` 0.0 is mono, 1.0 (the default) is unchanged, above 1.0 is wider, up to 3.0. Mono input is upmixed to stereo first.

```bash
# Widen to 1.5x
curl -X POST http://localhost:8000/v1/audio/stereo-width \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/mix.wav","width":1.5,"output_path":"out/wide.wav"}'

# Collapse to mono
curl -X POST http://localhost:8000/v1/audio/stereo-width \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/mix.wav","width":0.0,"output_path":"out/mono.wav"}'

# Subtle narrowing for the mix bus
curl -X POST http://localhost:8000/v1/audio/stereo-width \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"master/mix.wav","width":0.8,"output_path":"master/narrow.wav"}'
```

To measure the stereo image instead of changing it, use `POST /v1/audio/stereo-field` ([analysis](analysis.md)).

## Mid/side encode and decode

`POST /v1/audio/mid-side` converts left/right stereo to mid/side (`"mode": "encode"`) or back (`"mode": "decode"`). `mode` is required. Use it for width surgery outside the pedalboard chain: encode, process the mid or side channel, decode. Both directions need a two-channel input; a mono file gets a 400.

```bash
# Encode L/R to M/S
curl -X POST http://localhost:8000/v1/audio/mid-side \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/stereo.wav","mode":"encode","output_path":"out/ms_encoded.wav"}'

# Decode back to L/R
curl -X POST http://localhost:8000/v1/audio/mid-side \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"out/ms_encoded.wav","mode":"decode","output_path":"out/restored.wav"}'
```

## Errors

A missing engine (for example `fx-chain` removed with `AUDIOLLA_ENABLED_ENGINES`, see [configuration](configuration.md)) returns 404 with `"<slug> engine not configured"`. An unsupported `output_format` returns 415. A bad parameter value returns 400 with a `detail` that names the field. The [engines](engines.md) page lists which slugs ship in the CPU and CUDA images; every engine used on this page ships in both.
