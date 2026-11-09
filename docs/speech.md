---
title: "Speech"
description: "Clean up voice recordings with DeepFilterNet, find speech with silero-vad, and label who spoke when with pyannote speaker diarization."
nav_order: 9
---

# Speech

Three endpoints work on spoken audio: neural enhancement with DeepFilterNet (`/v1/audio/enhance/{engine}`), voice activity detection with silero-vad (`/v1/audio/vad`), and speaker diarization with pyannote (`/v1/audio/diarize/{engine}`). All three engines are in both the CPU and the CUDA image.

Inputs follow the usual `file_path` xor `file_url` contract from [Getting started](getting-started.md#input-and-output). Enhancement produces audio, so it also needs `output_path` or `output_url` (or `async_job`, see [Async jobs and webhooks](jobs.md)). VAD and diarization return JSON and take no output fields. For noise that is not speech-specific (hum, hiss, broadband noise on music), see [Separation and restoration](separation-and-restoration.md).

## Neural speech and vocal enhancement

`POST /v1/audio/enhance/deepfilter` runs DeepFilterNet (DF3), a noise suppression model trained on speech. Use it on voice recordings: podcasts, interviews, vocal takes. The DF3 weights download on first use.

```bash
# enhance a vocal recording
curl -X POST http://localhost:8000/v1/audio/enhance/deepfilter \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/vocal_recording.wav","output_path":"out/enhanced.wav"}'
# -> {"path":"out/enhanced.wav","size":...,"engine":"deepfilter","output_format":"wav"}
curl -o enhanced.wav http://localhost:8000/v1/files/out/enhanced.wav

# stage the output as mp3
curl -X POST http://localhost:8000/v1/audio/enhance/deepfilter \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "vocals/raw.wav",
    "output_format": "mp3",
    "output_path": "vocals/enhanced.mp3"
  }'
```

There are no tuning parameters, only the output fields (`output_format`, `output_path`, `output_url`, `async_job`, `webhook_url`). `deepfilter` is the only engine this path accepts; another configured slug gets 400 and an unknown one 404.

## Voice activity detection

`POST /v1/audio/vad` finds the speech in a recording with silero-vad. The audio is resampled to 16 kHz mono for detection. The response lists speech and non-speech segments with timestamps, plus the share of the file that is speech.

```bash
curl -X POST http://localhost:8000/v1/audio/vad \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/interview.wav"}'
# -> {
#      "speech_segments": [
#        {"start_sec": 1.2, "end_sec": 8.4, "duration_sec": 7.2},
#        ...
#      ],
#      "non_speech_segments": [
#        {"start_sec": 0.0, "end_sec": 1.2, "duration_sec": 1.2},
#        ...
#      ],
#      "speech_ratio": 0.73,
#      "duration": 120.0,
#      "threshold": 0.5
#    }

# tighter detection
curl -X POST http://localhost:8000/v1/audio/vad \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/podcast.wav",
    "threshold": 0.7,
    "min_speech_duration_ms": 300,
    "min_silence_duration_ms": 200
  }'
```

Parameters: `threshold` (speech probability cutoff, default `0.5`), `min_speech_duration_ms` (default `250`), `min_silence_duration_ms` (default `100`). The request runs synchronously and returns the JSON directly; it does not take `async_job`.

## Speaker diarization

`POST /v1/audio/diarize/pyannote` runs the `pyannote/speaker-diarization-3.1` pipeline and returns who spoke when: one segment per speaker turn, the list of speaker labels, and the speaker count.

The pyannote model is gated on Hugging Face. Before it works you need to:

1. Accept the model terms at [huggingface.co/pyannote/speaker-diarization-3.1](https://huggingface.co/pyannote/speaker-diarization-3.1) with your Hugging Face account.
2. Start the container with a token that can read it, as `HF_TOKEN` or `HUGGINGFACE_TOKEN`. The entrypoint copies whichever one you set into the other name, so one is enough. A read-only token works.

```bash
docker run --rm \
  -v $HOME/.audiolla-data:/data \
  -e HF_TOKEN=hf_your_token_here \
  -p 127.0.0.1:8000:8000 \
  psyb0t/audiolla:latest
```

Without a token, the first diarization request fails with an error that names `HUGGINGFACE_TOKEN`. The weights download into `HF_HOME` (`/data/hf` in the images) on first use. See [Configuration](configuration.md) for the token variables.

```bash
curl -X POST http://localhost:8000/v1/audio/diarize/pyannote \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/interview.wav"}'
# -> {
#      "segments": [
#        {"speaker": "SPEAKER_00", "start_sec": 0.5, "end_sec": 8.2, "duration_sec": 7.7},
#        {"speaker": "SPEAKER_01", "start_sec": 8.5, "end_sec": 14.1, "duration_sec": 5.6},
#        ...
#      ],
#      "num_speakers": 2,
#      "speakers": ["SPEAKER_00", "SPEAKER_01"],
#      "duration": 120.0
#    }

# hint the exact speaker count
curl -X POST http://localhost:8000/v1/audio/diarize/pyannote \
  -H 'Content-Type: application/json' \
  -d '{"file_path":"uploads/roundtable.wav","num_speakers":4}'

# or constrain the range
curl -X POST http://localhost:8000/v1/audio/diarize/pyannote \
  -H 'Content-Type: application/json' \
  -d '{
    "file_path": "uploads/panel.wav",
    "min_speakers": 2,
    "max_speakers": 6
  }'
```

Parameters: `num_speakers` (exact count), `min_speakers`, `max_speakers`, all optional. `duration` in the response is the end time of the last speaker turn, not the length of the file, so trailing silence is not counted. Like VAD, diarization runs synchronously and does not take `async_job`.
