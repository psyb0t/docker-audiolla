---
title: "MCP server"
description: "The audiolla MCP endpoint at /v1/mcp: transport, auth, client setup, the 82 tools, and how audio output works over MCP."
nav_order: 18
---

# MCP server

audiolla runs a [Model Context Protocol](https://modelcontextprotocol.io) server at `/v1/mcp` on the same port as the REST API. Point an MCP client at it and the agent gets the audio tools as callable functions: stem separation, chord detection, MIDI transcription, diarization, MIDI composition, tag editing, job control and file staging. The server is built in [`src/audiolla/mcp_server.py`](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/mcp_server.py).

## Connecting

- URL: `http://localhost:8000/v1/mcp`
- Transport: Streamable HTTP, stateless (`stateless_http=True`), JSON responses instead of SSE streams (`json_response=True`). There are no sessions to keep alive.
- Path: the FastMCP app is mounted at `/v1/mcp` with its own path set to `/`, so clients connect to `/v1/mcp`, not `/v1/mcp/mcp`. A small middleware rewrites the bare `/v1/mcp` to `/v1/mcp/` before routing, so the mount never answers with a 307 redirect.
- Auth: when `AUDIOLLA_AUTH_TOKEN` is set, `/v1/mcp` needs the same `Authorization: Bearer <token>` header as the REST API. See [security](security.md).

A client entry for a Streamable HTTP MCP client looks like this (the key names differ a little between clients):

```json
{
  "mcpServers": {
    "audiolla": {
      "type": "http",
      "url": "http://localhost:8000/v1/mcp",
      "headers": {
        "Authorization": "Bearer your-token-here"
      }
    }
  }
}
```

Drop the `headers` block when the server runs without a token. For clients that only speak stdio, the OpenClaw plugin bridges to this endpoint; see [agent integrations](agent-integrations.md).

## How tools take input and give output

Input works like the REST API: pass exactly one of `file_path` (a path in the [staging area](files.md)) or `file_url` (a URL the server fetches, allowed only by `AUDIOLLA_FETCH_MODE`). Neither or both raises a tool error.

Most audio-producing tools need exactly one of `output_path` (written under the staging area, result `{path, size, ...}`) or `output_url` (a presigned PUT URL, result `{url, size, ...}`). Neither or both raises a tool error. There is no inline base64 audio in the results of these tools; fetch a staged result with REST `GET /v1/files/<path>`.

Exceptions, as the code stands:

- `separate` takes per-stem maps instead: `output_paths={"vocals": "out/vocals.wav", ...}` or `output_urls={...}`. Each map must cover every stem the engine returns. The result is `staged_stems` or `uploaded_stems`.
- Only `output_url`, no `output_path`: `restore`, `enhance`, `deess`, `audio_thumbnail`, `midi_transform`, `midi_quantize`, `midi_humanize`, `drum_pattern`, `chords_to_midi`. Calling them without `output_url` fails. For a staged result, use the REST endpoint.
- Only `output_path`, no `output_url`: `stretch`.
- No output argument at all, so the tool always fails after doing the work: `hpss`, `slice_at_beats`, and `split` (which is marked deprecated). Use `POST /v1/audio/separate/hpss`, `POST /v1/audio/beat-slice` and `POST /v1/audio/split` instead.
- `beats` with `click_track=true`, `melody` with `as_midi=true` and `silence` with a `trim_mode` return the extra audio inline as base64 in `click_track_base64`, `midi_base64` and `trimmed_audio_base64`. Without those options they return JSON only.
- `audio_thumbnail`, `chords_to_midi`, `deess`, `drum_pattern` and `midi_humanize` upload to `output_url` with a plain HTTP client, not through the fetch policy, and do not check the upload's status code. See [security](security.md) for what the fetch policy normally blocks.

MCP tools run inline. There is no `async_job` option on MCP; long generations or separations hold the call open. Submit those through REST with `async_job: true` and use the job tools below to follow them.

## File tools

| Tool | What it does |
| --- | --- |
| `list_files` | Lists the staging area. |
| `put_file` | Writes `content_base64` to `path`. The base64 is decoded strictly and the decoded size is capped at `AUDIOLLA_MAX_UPLOAD_BYTES`. |
| `get_file` | Returns `{path, size}` for a staged file. It does not return the content; download it with `GET /v1/files/<path>`. Files over `AUDIOLLA_MAX_UPLOAD_BYTES` are refused. |
| `delete_file` | Deletes a staged file. |

Paths go through the same sanitizer as REST (`sanitize_path` and `resolve_under` in [`src/audiolla/files.py`](https://github.com/psyb0t/docker-audiolla/blob/main/src/audiolla/files.py)), so they cannot leave the staging area.

## Tools

The server registers 82 tools. Names and arguments below come from the function signatures in `mcp_server.py`; the server logs the live count at startup (`mcp server initialised: N tools`).

### Discovery, workflows and jobs

| Tool | What it does |
| --- | --- |
| `list_engines` | Configured engines and whether each is loaded. |
| `list_presets` | Curated server-side workflows, name and description. |
| `describe_preset` | The full step list of one preset. |
| `list_ops` | Pipeline op slugs usable in `run_pipeline_tool` and presets. |
| `run_preset` | Runs a preset on an input. Result includes the `steps` log. |
| `run_pipeline_tool` | Runs an ad-hoc `steps=[{op, params}, ...]` chain server-side. |
| `list_jobs` | Lists async jobs, optional `status` filter (`pending`, `running`, `completed`, `failed`, `cancelled`). |
| `get_job` | Status and result of one job by `job_id`. |
| `cancel_job` | Cancels a running job or removes a finished one. |

See [workflows](workflows.md) and [jobs](jobs.md).

### Separation, restoration and speech

| Tool | What it does |
| --- | --- |
| `separate` | Stem separation with a Demucs or UVR `engine` and a `stems` list. Output through `output_paths` or `output_urls`. |
| `hpss` | Harmonic and percussive split. Has no output argument, so it fails; use REST. |
| `restore` | UVR de-reverb, de-echo or de-noise (`engine`, default `uvr-dereverb`; `aggressive=true` for the hard de-echo model). `output_url` only. |
| `denoise` | UVR MelBand Roformer de-noise (`engine` default `uvr-denoise`). |
| `noise_reduce` | `engine=noise-reduce` (DSP, `stationary`, `prop_decrease`) or `engine=uvr-denoise` (ML). |
| `enhance` | DeepFilterNet speech and vocal enhancement. `output_url` only. |
| `repair_audio` | Declip and dehum (`declip`, `dehum`, `hum_freq` 50 or 60). |
| `vad` | silero-vad speech and non-speech segments with timestamps and speech ratio. |
| `diarize` | pyannote speaker diarization (`num_speakers`, `min_speakers`, `max_speakers`). Needs a Hugging Face token. |

### Mastering, dynamics and effects

| Tool | What it does |
| --- | --- |
| `master` | `mode` reference (matchering, `reference_path` or `reference_url`) or chain (pedalboard `preset`). |
| `normalize` | Normalizes to `target_lufs` (default -14). |
| `transform` | Sox DSP chain from an `operations` list. |
| `fx` | Pedalboard effects chain from an `effects` list. |
| `multiband_compress` | N-band compressor: `crossovers_hz` (N values) and `bands` (N+1 specs with `threshold_db`, `ratio`, optional `attack_ms`, `release_ms`, `makeup_db`). |
| `transient_shaper` | `attack_gain_db` and `sustain_gain_db`. |
| `deess` | Split-band de-esser (`threshold_db`, `frequency_hz`, `ratio`). `output_url` only. |
| `sidechain_duck` | Ducks the primary input while the trigger (`trigger_file_path` or `trigger_file_url`) is loud. |
| `convolution_reverb` | Impulse-response reverb (`ir_file_path` or `ir_file_url`, `wet_mix` 0.0 to 1.0). |
| `eq` | Parametric EQ, `bands` of `{freq, gain_db, width_hz}`. |
| `pan` | `position` from -1.0 (left) to 1.0 (right). |
| `stereo_width` | M/S width, 0.0 (mono) to 3.0. |
| `mid_side` | `mode=encode` (L/R to M/S) or `mode=decode`. |

### Editing, time and pitch

| Tool | What it does |
| --- | --- |
| `trim` | Cuts to `[start_sec, end_sec)`. |
| `mix` | Mixes `tracks`, a list of `{file_path or file_url, gain_db}`, at least two. |
| `concat` | Joins `files`, a list of `{file_path or file_url}`, at least two. |
| `speed` | Playback speed without pitch change, `speed` 0.1 to 10.0. |
| `convert` | Re-encodes: `output_format`, `sample_rate`, `channels`. |
| `fade` | `fade_in` and `fade_out` seconds with a `curve`. |
| `reverse` | Plays backwards. |
| `loop` | Repeats `count` times in total, at least 2. |
| `split` | Deprecated; always raises. Use REST `POST /v1/audio/split`. |
| `slice_at_beats` | Has no output argument, so it fails; use REST `POST /v1/audio/beat-slice`. |
| `audio_thumbnail` | The most active `duration_sec` segment, with `start_sec` and `end_sec`. `output_url` only. |
| `stretch` | `tempo_factor` and `pitch_semitones` through the librosa phase vocoder. `output_path` only. |
| `pitch_correct` | Pulls notes toward the nearest semitone, `strength` 0.0 to 1.0. |
| `bpm_match` | Detects BPM and stretches to `target_bpm`. |
| `key_match` | Detects the key and shifts to `target_key`. |

### Analysis

| Tool | What it does |
| --- | --- |
| `analyze` | librosa features: BPM, key, loudness, duration, spectral features. |
| `beats` | Tempo and beat times; `click_track=true` adds `click_track_base64`. |
| `onsets` | Onset times and strengths. |
| `melody` | pyin pitch contour; `as_midi=true` adds `midi_base64`. |
| `segments` | Structural segments with repeating labels (`num_segments`). |
| `silence` | Silent ranges; `trim_mode` `edges` or `all` adds `trimmed_audio_base64`. |
| `chords` | Key and time-stamped chords. |
| `loudness` | Integrated LUFS, JSON only. |
| `loudness_curve` | RMS envelope over time (`hop_length`). |
| `info` | ffprobe metadata. |
| `fingerprint` | Chromaprint fingerprint (`analyze_seconds`, `return_raw`). |
| `tag` | Top-K AudioSet labels (`top_k`). |
| `embed` | 512-dim CLAP embedding; `query_text` adds a similarity score. |
| `classify` | Zero-shot CLAP scores for your `labels`. |
| `similar` | CLAP cosine similarity against `reference_file_path` or `reference_file_url`. |
| `detect_clipping` | Clipping count, ratio and peak. |
| `stereo_field` | L/R correlation, width, balance and mono compatibility. |
| `dj_prep` | BPM, key, Camelot position and integrated LUFS. |
| `find_loop_point` | Best loop boundary (`min_loop_bars`, `num_candidates`). |
| `audio_metadata` | Reads tags; with `tags` it writes them and returns the new set. |
| `visualize` | PNG spectrogram or waveform, or animated video (`mode`, `width`, `height`, `color`, `scale`, `fps`, `container`). |

### MIDI and generation

| Tool | What it does |
| --- | --- |
| `audio_to_midi` | basic-pitch polyphonic transcription with its threshold options. |
| `midi_compose` | JSON song `spec` to MIDI. |
| `midi_inspect` | MIDI structure as JSON. |
| `midi_transform` | Transpose, quantize, tempo override, keep or drop channels. `output_url` only. |
| `midi_quantize` | Snaps notes to `grid_beats`. `output_url` only. |
| `midi_humanize` | Timing and velocity jitter (`timing_ms`, `velocity_pct`, `seed`). `output_url` only. |
| `midi_render` | MIDI to audio through fluidsynth and a SoundFont. |
| `midi_generate` | Compose and render in one call. |
| `drum_pattern` | Step-sequencer `pattern` to General MIDI drums (`tempo_bpm`, `steps`, `bars`, `swing`). `output_url` only. |
| `chords_to_midi` | Detected chords to a MIDI progression. `output_url` only. |
| `generate_music` | Text to audio with `engine` `stable-audio-open`, `musicgen-small`, `musicgen-medium`, `riffusion` or `audioldm2`; `prompt` is required. MusicGen needs `AUDIOLLA_ENABLE_NONCOMMERCIAL=1`. All five need the CUDA image. |

### Files

`list_files`, `put_file`, `get_file`, `delete_file`: see [file tools](#file-tools).

## Errors

A tool reports failure by raising, which the MCP client shows as a tool error with the message: an unknown engine, a missing input, a bad path, a fetch refused by the policy, or the engine's own error text.
