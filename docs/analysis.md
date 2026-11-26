---
title: "Analysis"
description: "Measure audio over HTTP: BPM, key, LUFS, beats, onsets, melody, chords, silence, fingerprints, CLAP embeddings, AudioSet tags and stereo field."
nav_order: 8
---

# Analysis

Measure tempo, key, loudness, timing or the content of a recording. Use [file staging](files.md) to reuse the same input across calls. The individual operations in the [REST API](api.md) document the request fields and response formats.

## Analyze

Start here for a track's tempo, key and loudness. A result can be `null` if the calculation fails or the feature was omitted.

API reference: [Analyze audio](/reference/analyze/).

## Beats, onsets, melody, segments

Beats locate the musical grid. Onsets locate attacks independently of that grid. Melody tracks pitch over time, while segments mark recurring sections. A rendered click track lets you check the beat grid by ear. For a usable note file, export the tracked melody as MIDI. When no destination is provided, the optional click track and melody MIDI are returned in the JSON response as `click_track_base64` and `midi_base64`.

API reference: [Beats](/reference/beats/), [Onsets](/reference/onsets/), [Melody](/reference/melody/), [Segments](/reference/segments/).

## Silence detection and trimming

Measure gaps before editing. Trim the edges to preserve pauses in conversation, or remove all detected gaps to tighten a recording. A trim without a destination returns the result in `trimmed_audio_base64`.

API reference: [Detect silence](/reference/silence/).

## Acoustic fingerprint

Use Chromaprint to identify the recording across different encodings. Use embeddings if you need to find recordings that sound similar.

API reference: [Fingerprint audio](/reference/fingerprint/).

## Chord and key detection

Estimate the key and locate major and minor chord changes. Use [chords to MIDI](midi.md#chords-to-midi) to play the progression back or import it into a DAW.

API reference: [Detect chords](/reference/chords/).

## Loudness measurement

Measure integrated loudness in LUFS. Use [normalization](mastering-and-effects.md#loudness-normalization) to change the level.

API reference: [Measure loudness](/reference/loudness/).

## Loudness curve

Use windowed RMS over time to locate quiet or loud passages. Use integrated LUFS when you need a single value for the whole track.

API reference: [Get a loudness curve](/reference/loudness-curve/).

## Audio tagging

Use the AudioSet label vocabulary to identify common sounds such as speech or instruments. The model weights download on first use unless already cached.

API reference: [Tag audio](/reference/tag/).

## Audio embeddings

Use CLAP vectors for search and clustering, or score an audio clip against a text prompt. See [Engines](engines.md) for model setup.

API reference: [Embed audio](/reference/embed/).

## Zero-shot classification

Give CLAP your own label names when the predefined AudioSet labels are too general. The scores rank the labels for the input.

API reference: [Classify audio](/reference/classify/).

## Audio info

Probe the encoded file for sample rate, channels and other metadata before processing it.

API reference: [Get audio info](/reference/audio-info/).

## Similar

Compare two clips using CLAP. This measures similarity in their content, while an acoustic fingerprint helps identify the same recording.

API reference: [Compare audio](/reference/similar/).

## Loop point

Find candidate loop boundaries on the beat grid. Listen to the cut before repeating it. Short files may return no candidate for the requested length.

API reference: [Find loop points](/reference/loop-point/).

## Clip detection

Scan for samples near full scale. Use [repair](separation-and-restoration.md#repair) when the recording needs declipping.

API reference: [Detect clipping](/reference/clip-detect/).

## DJ prep

Get the tempo, key, Camelot position and integrated loudness together for selecting and mixing tracks.

API reference: [Prepare a DJ track](/reference/dj-prep/).

## Stereo field analysis

Check left and right balance and phase correlation before downmixing. Negative correlation can signal cancellation when played in mono.

API reference: [Analyze the stereo field](/reference/stereo-field/).
