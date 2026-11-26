---
title: "MIDI"
description: "Audio-to-MIDI with basic-pitch, JSON song specs to MIDI, drum step patterns, chord MIDI, inspect, transform, quantize, humanize and FluidSynth rendering."
nav_order: 12
---

# MIDI

Turn a recording into notes, compose from a JSON score, edit a MIDI file or render it through a SoundFont. Compose, generate and drum take the score or pattern as the body and place output options in the query string. With no destination, they return the file bytes directly.

## Audio-to-MIDI transcription

Use Basic Pitch to detect notes in a recording. Inspect the result before rendering, particularly on dense or noisy inputs.

API reference: [Transcribe audio to MIDI](/reference/to-midi/).

## Compose MIDI

Send a score with note positions in beats. Channel 9 uses General MIDI percussion note numbers. Stage the output to pass it to another Audiolla operation. These fields describe the score shared by compose and generate.

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

API reference: [Compose a MIDI file](/reference/midi-compose/).

## Inspect MIDI

Read the tracks, channels, tempo events and note ranges before transforming or rendering.

API reference: [Inspect MIDI](/reference/midi-inspect/).

## Transform MIDI

Transpose, re-tempo, quantize or filter tracks by channel. Transposition skips the drum channel and drops notes outside the MIDI pitch range.

API reference: [Transform MIDI](/reference/midi-transform/).

## MIDI quantize

Snap note starts to a grid measured in beats. A grid of `0.25` is a sixteenth note in 4/4.

API reference: [Quantize MIDI](/reference/midi-quantize/).

## MIDI humanize

Add small timing and velocity variations. Fix the seed to repeat the result. Use a staged MIDI file for input.

API reference: [Humanize MIDI](/reference/midi-humanize/).

## Render MIDI to audio

Render with FluidSynth. Both images ship FluidR3_GM. Stage your own SoundFont if the part needs different instruments.

API reference: [Render MIDI](/reference/midi-render/).

## Generate music from a spec

Compose and render the same score in one call when you only need the audio result.

API reference: [Compose and render](/reference/midi-generate/).

## Drum pattern

Each voice has a step sequence. Zero is a rest, one is a hit at the default velocity, and larger values specify the velocity. Swing delays alternating steps.

API reference: [Write a drum pattern](/reference/midi-drum/).

## Chords to MIDI

Export detected chord segments as sustained MIDI chords. Set the target tempo yourself. The chord conversion does not estimate it.

API reference: [Convert chords to MIDI](/reference/chords-to-midi/).
