---
title: "Speech"
description: "Clean up voice recordings with DeepFilterNet, find speech with silero-vad, and label who spoke when with pyannote speaker diarization."
nav_order: 9
---

# Speech

Enhance the recording, find the time ranges that contain speech, or mark who spoke when. Use [Talkies](https://psyb0t.github.io/docker-talkies/) for transcription.

## Neural speech and vocal enhancement

Use DeepFilterNet to reduce noise in a voice recording before transcription or mixing.

API reference: [Enhance speech](/reference/audio-enhance/).

## Voice activity detection

Use Silero VAD to locate speech and non-speech time ranges. It describes the recording without rewriting it.

API reference: [Detect speech](/reference/vad/).

## Speaker diarization

Use pyannote to assign speaker labels to time ranges. A known speaker count can help separate overlapping voices. Accept the [pyannote model terms](https://huggingface.co/pyannote/speaker-diarization-3.1) before enabling it, then provide a Hugging Face read token as described in [Configuration](configuration.md).

API reference: [Diarize a recording](/reference/diarize/).
