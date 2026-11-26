---
title: "Editing, time and pitch"
description: "Trim, mix, concat, fade, loop, split and slice audio, change speed, tempo, pitch and key, write tags, and render spectrograms, waveforms and videos."
nav_order: 10
---

# Editing, time and pitch

Use these operations to cut, join, re-encode and reshape recordings. See [input and output](getting-started.md#input-and-output) for how to pass staged files and save results.

## Trim

Cut a time range out of a recording. Leave the end open to keep everything after the start.

API reference: [Trim audio](/reference/trim/).

## Mix

Mix simultaneous tracks. Inputs are summed at unity gain, so loud overlapping tracks can clip. Adjust the levels before mixing. Use [remix](separation-and-restoration.md#remix-stems) for per-stem levels on a single recording.

API reference: [Mix tracks](/reference/mix/).

## Concat

Join files end to end in input order. Use mixing when the inputs should play at the same time.

API reference: [Concatenate files](/reference/concat/).

## Speed

Change playback speed while keeping pitch. Use [time-stretch and pitch-shift](#time-stretch-and-pitch-shift) to adjust both in one request.

API reference: [Change speed](/reference/speed/).

## Convert

Re-encode a file or change its channel count or sample rate.

API reference: [Convert audio](/reference/convert/).

## Fade

Smooth the beginning or end of a clip. Use the request schema to compare the supported fade curves.

API reference: [Apply fades](/reference/fade/).

## Reverse

Play the recording backwards.

API reference: [Reverse audio](/reference/reverse/).

## Loop

Repeat the entire recording. The count is the total number of plays. Use [loop point analysis](analysis.md#loop-point) to find a good cut first.

API reference: [Loop audio](/reference/loop/).

## Split

Get a ZIP with equal-length pieces or split the recording on silence. The silent-gap mode uses the silence detection engine.

API reference: [Split audio](/reference/split/).

## Beat slice

Get a ZIP of beat-aligned slices. Anything before the first detected beat is omitted.

API reference: [Slice on beats](/reference/beat-slice/).

## Audio thumbnail

Pick the most active window for a preview or teaser.

API reference: [Make an audio thumbnail](/reference/thumbnail/).

## Time-stretch and pitch-shift

Adjust tempo and pitch independently. Use it to slow a passage or move a vocal into another key.

API reference: [Stretch audio](/reference/stretch/).

## Pitch correct

Correct a recording that is consistently sharp or flat. This applies one shift to the whole recording.

API reference: [Correct pitch](/reference/pitch-correct/).

## BPM match

Detect the source tempo, then stretch to the target tempo. The request fails if the source tempo cannot be detected.

API reference: [Match BPM](/reference/bpm-match/).

## Key match

Detect the source key and shift by the shortest interval to the target root. Mode suffixes do not change the target root.

API reference: [Match key](/reference/key-match/).

## Audio metadata tags

Read or update file tags without re-encoding. Supply an output destination to persist the change. The `tags` field holds JSON encoded as a string.

API reference: [Read or edit metadata](/reference/audio-metadata/).

## Visualize (spectrogram, waveform, video)

Use a spectrogram for frequency content, a waveform for the amplitude envelope, or an animated visualization with the original audio muxed in.

API reference: [Spectrogram](/reference/visualize-spectrogram/), [Waveform](/reference/visualize-waveform/), [Video](/reference/visualize-video/).

## Errors

See [Troubleshooting](troubleshooting.md#requests-fail) for unavailable engines, invalid requests and output format errors.
