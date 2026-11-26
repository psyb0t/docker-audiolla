---
title: "Mastering, dynamics and effects"
description: "Reference and preset mastering, LUFS normalization, pedalboard and SoX chains, multiband compression, de-essing, ducking, EQ, pan and stereo width."
nav_order: 7
---

# Mastering, dynamics and effects

Choose reference mastering for a whole mix, or pick an individual effect for a specific problem. To run several effects in order, see [presets and pipelines](workflows.md).

## Master

Reference mastering matches the EQ and loudness of another track. Chain mastering runs a fixed pedalboard preset. Audiolla infers the mode from the reference or preset when you omit `mode`.

API reference: [Master a track](/reference/master/).

## Loudness normalization

Adjust the gain to a target LUFS. Use the measurement endpoint to check a track without changing it.

API reference: [Normalize loudness](/reference/normalize/), [Measure loudness](/reference/loudness/).

## Transform (SoX)

Apply a series of SoX operations in order. Each step has an operation name and its parameters.

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

API reference: [Run SoX transforms](/reference/transform/).

## Effects chain (pedalboard)

Build a custom chain from the [allowed pedalboard effects](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/engines/fx_chain.py). The params are the effect constructor's keyword arguments. External plugins are disabled.

API reference: [Apply an effects chain](/reference/fx/).

## Multiband compression

Compress different frequency ranges independently. Supply one band for each interval defined by your crossovers, including the lowest and highest intervals.

API reference: [Compress by band](/reference/multiband-compress/).

## Transient shaper

Raise the attack for punchier drums, or reduce sustain to shorten their tails.

API reference: [Shape transients](/reference/transient/).

## De-ess

Reduce sibilance by compressing the high-frequency band while leaving the rest of the signal alone.

API reference: [De-ess audio](/reference/deess/).

## Sidechain duck

Lower music in response to a narration track. The output contains the processed music. Mix in the narration afterward.

API reference: [Duck audio](/reference/sidechain-duck/).

## Convolution reverb

Stage an impulse response to give a track the sound of a room or another recorded acoustic space.

API reference: [Apply a convolution reverb](/reference/conv-reverb/).

## EQ

Cut or boost frequency bands. For mains hum, also see [repair](separation-and-restoration.md#repair).

API reference: [Apply EQ](/reference/eq/).

## Pan

Move a source left or right in the stereo field. Mono inputs produce stereo output.

API reference: [Pan audio](/reference/pan/).

## Stereo width

Widen a mix or collapse it to mono. Use [stereo field analysis](analysis.md#stereo-field-analysis) to check the result.

API reference: [Adjust stereo width](/reference/stereo-width/).

## Mid/side encode and decode

Convert left and right into mid and side channels for separate processing, then decode them back to stereo. Start with a two-channel file.

API reference: [Convert mid and side](/reference/mid-side/).

## Errors

See [Troubleshooting](troubleshooting.md#requests-fail) for missing engines and rejected requests.
