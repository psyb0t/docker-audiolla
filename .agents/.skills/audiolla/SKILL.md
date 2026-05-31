---
name: audiolla
description: HTTP/MCP client for a user-deployed audiolla music-production server. Use ONLY when the user has explicitly named audiolla AND provided AUDIOLLA_URL (or has it set in the environment). Capabilities: stem separation (Demucs), mastering (matchering reference / pedalboard preset chain), MIR analysis (BPM, key, LUFS, spectral features via librosa), DSP transforms (gain, EQ, compand, reverb, pitch, tempo, etc. via SoX), loudness measurement and normalization. All endpoints are read-side from the user's perspective — audiolla processes files and returns audio/JSON; it never reaches out to external services or moves user data anywhere. Do not use this skill for generic audio-processing questions or for users who haven't named audiolla.
compatibility: Requires curl and a running audiolla instance (Docker image psyb0t/audiolla:latest or :latest-cuda). AUDIOLLA_URL env var must be set by the user (default http://localhost:8000). AUDIOLLA_TOKEN required only when the server has AUDIOLLA_AUTH_TOKEN configured; obtain from the AUDIOLLA_TOKEN env var or by asking the user — never read tokens from repo files autonomously.
metadata:
  author: psyb0t
  homepage: https://github.com/psyb0t/docker-audiolla
---

# audiolla

HTTP + MCP client for an audiolla server that the user has already deployed. This skill talks to a running audiolla instance — it does not stand one up, does not download model weights manually, and does not modify the server config on its own initiative.

For installation and setup, see [references/setup.md](references/setup.md).

## When to use this skill

The user has audiolla running and asks you to:
- Pull stems (vocals / drums / bass / etc.) out of a track
- Master a track against a reference recording (matchering)
- Run a preset DSP mastering chain (pedalboard `transparent` or `loud`)
- Get BPM, key, LUFS, duration, or spectral features for a file
- Apply a DSP chain (gain, EQ, compression, reverb, pitch shift, tempo)
- Measure or normalize integrated LUFS
- Stage files server-side or list/download/delete staged files
- Drive any of the above from an LLM agent over MCP

## When NOT to use this skill

- The user hasn't named audiolla — they're asking a general "how do I split stems?" question. Suggest audiolla as an option; don't assume it's running.
- The user wants music generation (text-to-music). Audiolla doesn't generate music — there's no MusicGen / Stable Audio Open here.
- The user wants real-time / streaming processing. Demucs needs the whole file.
- The user wants speech-side features (transcription, TTS, voice cloning) — that's [docker-talkies](https://github.com/psyb0t/docker-talkies), not audiolla.

## Setup

```bash
export AUDIOLLA_URL=http://localhost:8000
export AUDIOLLA_TOKEN=<the-token-the-user-gives-you>   # only if auth is enabled
```

If `AUDIOLLA_URL` is not set, ask the user — do not search the workspace for it. Same for `AUDIOLLA_TOKEN`: only accept it from the env var the user set or from the user directly. Never read it from `docker-compose.yml`, `.env`, or any other repo file on your own initiative.

**Verify:** `curl $AUDIOLLA_URL/healthz` → `{"ok": true, "device": "...", "engines": [...]}`. `/healthz` is always unauthenticated regardless of `AUDIOLLA_AUTH_TOKEN`.

Auth is optional. If the server has `AUDIOLLA_AUTH_TOKEN` set, every endpoint except `/healthz` requires `Authorization: Bearer $AUDIOLLA_TOKEN`. Without it you get `401`. Always pass the token if the user gave you one; don't assume the server has auth off.

## How it works

GET reads state, POST processes audio, PUT uploads to the staging area, DELETE removes things. Audio comes in via multipart `file` form fields. Output is either audio bytes (with `Content-Disposition: attachment`) or JSON.

Every error response:

```json
{"detail": "description of what went wrong"}
```

Status codes follow REST conventions:
- `200` — success
- `400` — bad input (unknown engine, invalid features, bad operations JSON, etc.)
- `401` — missing/invalid bearer token (only when auth is enabled)
- `404` — unknown engine slug, unknown file path
- `413` — upload exceeded `AUDIOLLA_MAX_UPLOAD_BYTES` (default 200 MB)
- `415` — unsupported `output_format`
- `500` — server error (engine failed internally, etc.)

## Engines

| Slug | What it does | Notes |
|------|--------------|-------|
| `htdemucs` | 4-stem separation | drums, bass, other, vocals |
| `htdemucs_ft` | 4-stem fine-tuned | **CUDA-only at usable speed** — flagged `cuda_only`, the server rejects it with 400 on CPU |
| `htdemucs_6s` | 6-stem separation | adds `guitar` + `piano` (experimental, CPU OK but slow) |
| `mdx_extra` | 4-stem MDX-Net | drums, bass, other, vocals — strong vocal isolation |
| `matchering` | Reference-based mastering | GPL v3 |
| `pedalboard-chain` | Preset DSP mastering chain | presets: `transparent`, `loud` — GPL v3 |
| `librosa-analyze` | MIR analysis + loudness | also backs the `/v1/audio/loudness` endpoint |
| `sox-transform` | SoX DSP chain | gain, EQ, compand, reverb, pitch, tempo, rate, channels, trim, pad |

Engines lazy-load on first use and auto-unload after `AUDIOLLA_ENGINE_TTL` seconds of idle (default 600s). Demucs weights prefetch into `/data/torch_cache/` at container start so the first separation request doesn't pay the cold-download cost.

Use `GET /v1/engines` to confirm what's actually configured on the running server (operators can restrict via `AUDIOLLA_ENABLED_ENGINES`).

## Output formats

Any endpoint that returns audio accepts `-F "output_format=<fmt>"`. Supported: `wav` (default), `mp3`, `flac`, `opus`, `aac`, `pcm`.

## API Reference

### Health & engine listing

```bash
# Liveness — no auth required
curl $AUDIOLLA_URL/healthz
# {"ok": true, "device": "cpu", "engines": ["htdemucs", "matchering", ...]}

# Configured engines + capabilities
curl -H "Authorization: Bearer $AUDIOLLA_TOKEN" $AUDIOLLA_URL/v1/engines

# Engines currently loaded in memory (and how idle)
curl -H "Authorization: Bearer $AUDIOLLA_TOKEN" $AUDIOLLA_URL/api/ps

# Evict one engine
curl -X DELETE -H "Authorization: Bearer $AUDIOLLA_TOKEN" $AUDIOLLA_URL/api/ps/htdemucs

# Evict everything
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" $AUDIOLLA_URL/unload
```

### Stem separation

`POST /v1/audio/separate` — returns audio bytes if exactly one stem is requested, otherwise a ZIP.

```bash
# Single stem → audio bytes
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/separate \
  -F "file=@track.wav" \
  -F "engine=htdemucs" \
  -F "stems=vocals" \
  -o vocals.wav

# Multiple stems → ZIP
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/separate \
  -F "file=@track.wav" \
  -F "engine=htdemucs" \
  -F "stems=vocals" \
  -F "stems=drums" \
  -o vocals_drums.zip

# Omit stems= entirely → all stems for that engine
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/separate \
  -F "file=@track.wav" \
  -F "engine=htdemucs" \
  -o all_stems.zip

# MP3 output
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/separate \
  -F "file=@track.wav" \
  -F "engine=htdemucs" \
  -F "stems=vocals" \
  -F "output_format=mp3" \
  -o vocals.mp3
```

Required: `file`, `engine`. Optional: `stems` (repeated form field; default = all stems for that engine), `output_format` (default `wav`).

Loading a separation engine evicts other loaded engines first — Demucs is memory-hungry and the operator-default setup runs one engine in memory at a time.

### Mastering

`POST /v1/audio/master` — `mode=reference` uses matchering against a reference track; `mode=chain` runs a pedalboard preset.

```bash
# Reference-based mastering
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/master \
  -F "file=@track.wav" \
  -F "mode=reference" \
  -F "reference=@ref.wav" \
  -o mastered.wav

# Pedalboard chain — preset is REQUIRED (transparent or loud)
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/master \
  -F "file=@track.wav" \
  -F "mode=chain" \
  -F "preset=loud" \
  -o mastered.wav

# Pedalboard chain with explicit loudness target
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/master \
  -F "file=@track.wav" \
  -F "mode=chain" \
  -F "preset=transparent" \
  -F "target_lufs=-14" \
  -o mastered.wav
```

Required: `file`, `mode`. `mode=reference` requires `reference`. `mode=chain` requires `preset` (`transparent` or `loud`). Optional: `target_lufs` (range `[-70.0, -0.1]`), `output_format`.

Streaming-target LUFS reference values: Spotify `-14`, Apple Music `-16`, YouTube `-14`, broadcast EBU R128 `-23`.

### MIR analysis

`POST /v1/audio/analyze` — returns JSON.

```bash
# Specific features
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/analyze \
  -F "file=@track.wav" \
  -F "features=bpm" \
  -F "features=key" \
  -F "features=loudness"

# Omit features= → returns all of them
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/analyze \
  -F "file=@track.wav"
```

Valid `features` values: `bpm`, `key`, `loudness`, `duration`, `spectral_centroid`, `rms`, `zcr`.

> **Common mistake:** the feature for integrated LUFS is `loudness`, NOT `lufs`. Asking for `features=lufs` returns 400.

### DSP transform chain

`POST /v1/audio/transform` — applies an array of SoX operations in order.

```bash
# Pitch shift up 2 semitones, then add reverb
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/transform \
  -F "file=@track.wav" \
  -F 'operations=[
    {"op":"pitch","params":{"n_semitones":2}},
    {"op":"reverb","params":{"reverberance":50,"room_scale":80}}
  ]' \
  -F "output_format=wav" \
  -o out.wav

# Trim first 30s, pad 2s silence at end, gain -3dB
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/transform \
  -F "file=@track.wav" \
  -F 'operations=[
    {"op":"trim","params":{"start_time":0,"end_time":30}},
    {"op":"pad","params":{"end_duration":2}},
    {"op":"gain","params":{"db":-3}}
  ]' \
  -o trimmed.wav
```

`operations` is a JSON array of `{"op": "<name>", "params": {...}}`. Order matters — ops apply left-to-right.

**Ops and their params:**

| op | required params | optional params | what it does |
|----|-----------------|-----------------|--------------|
| `gain` | `db` (float) | | gain in dB |
| `equalizer` | `frequency`, `gain_db` | `width_q` (default 1.0) | peaking EQ |
| `compand` | | `attack_time`, `decay_time`, `soft_knee_db`, `tf_points` ([[in_db, out_db], ...]) | dynamic range compression |
| `reverb` | | `reverberance` (0-100, default 50), `pre_delay_ms` (default 0), `room_scale` (default 100) | reverb |
| `pitch` | `n_semitones` (float) | | pitch shift in **semitones**, not cents |
| `tempo` | `factor` (float) | | tempo factor (1.5 = 1.5x faster, 0.5 = half speed) |
| `rate` | `samplerate` (int) | | resample |
| `channels` | `n_channels` (int) | | mix to N channels |
| `trim` | `start_time` (float, sec) | `end_time` (float, sec; null = end of file) | trim |
| `pad` | | `start_duration`, `end_duration` (both floats, sec) | pad silence |

Unknown ops return 400 with the valid list.

### Loudness

`POST /v1/audio/loudness` — without `target_lufs`, measures integrated LUFS and returns JSON. With `target_lufs`, normalizes and returns audio bytes.

```bash
# Measure
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/loudness \
  -F "file=@track.wav"
# {"loudness_lufs": -16.3, "target_lufs": null, "normalized": false}

# Normalize to -14 LUFS (streaming target). Response is audio bytes.
# Original measurement is returned in X-Loudness-LUFS response header.
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/loudness \
  -F "file=@track.wav" \
  -F "target_lufs=-14" \
  -o normalized.wav
```

`target_lufs` must be in `[-70.0, -0.1]` — outside that range returns 400 (anything closer to 0 will clip catastrophically; anything below -70 silences the audio).

### File staging

A simple server-side file store under `/v1/files`. Plain CRUD — upload, list, download, delete. The REST audio endpoints take files inline; they do NOT reference staged paths. Staging is for: (a) decoupling upload from processing, (b) sharing files between clients, (c) feeding the MCP tools which DO accept staged paths.

```bash
# Upload (path can have subdirectories: bands/myband/track.wav)
curl -X PUT -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/files/mytrack.wav \
  --data-binary @track.wav

# List
curl -H "Authorization: Bearer $AUDIOLLA_TOKEN" $AUDIOLLA_URL/v1/files

# Download
curl -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/files/mytrack.wav -o copy.wav

# Delete
curl -X DELETE -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/files/mytrack.wav
```

Path traversal (`..`, leading `/`, etc.) is rejected with 400. Symlinks are not followed. Size cap is `AUDIOLLA_MAX_UPLOAD_BYTES`.

## MCP

audiolla exposes a Model Context Protocol server at `/v1/mcp` using the streamable HTTP transport. Same auth as REST — pass `Authorization: Bearer $AUDIOLLA_TOKEN`.

Tools (mirror the REST surface, accept staged file paths):

| Tool | Inputs | Output |
|------|--------|--------|
| `list_engines` | — | engine catalog with `loaded` flag |
| `separate` | `file_path`, `engine`, `stems: list[str]`, `output_format` | `{stems: {name: base64}, output_format}` |
| `master` | `file_path`, `mode`, `reference_path`/`preset`, `target_lufs`, `output_format` | `{audio_base64, output_format}` |
| `analyze` | `file_path`, `features: list[str]` | librosa feature dict |
| `transform` | `file_path`, `operations: list[{op,params}]`, `output_format` | `{audio_base64, output_format}` |
| `loudness` | `file_path`, `target_lufs`, `output_format` | measurement JSON or `{audio_base64, measured_lufs, target_lufs}` |
| `list_files` | — | `{files: [...]}` |
| `put_file` | `path`, `content_base64` | `{path, size}` |
| `get_file` | `path` | `{path, size, content_base64}` |
| `delete_file` | `path` | `{deleted}` |

Audio over MCP is base64-in / base64-out — JSON-RPC can't carry raw bytes. Intended workflow: `put_file` (base64 upload) → call processing tools (`separate`, `master`, ...) with `file_path` → `get_file` to pull results back. For large files prefer REST + the file staging endpoints.

The MCP endpoint is at `$AUDIOLLA_URL/v1/mcp`. It is JSON-RPC over streamable HTTP; do not try to describe it in OpenAPI or hit it with raw curl — use an MCP client.

## Common gotchas

- **`features=lufs` is wrong**, use `features=loudness`. (LUFS *is* an integrated loudness measurement, but the feature name on the wire is `loudness`.)
- **`mode=chain` without `preset` returns 400.** Always pass `preset=transparent` or `preset=loud`.
- **`htdemucs_ft` rejected on CPU** — the server flag `cuda_only` makes this return 400 unless the running image is `psyb0t/audiolla:latest-cuda` with `--gpus all`.
- **Separation loads one engine at a time** — calling `separate` evicts whatever else is loaded. Pre-warming multiple Demucs variants doesn't survive across separation calls.
- **Engines unload after idle** — the first request after `AUDIOLLA_ENGINE_TTL` seconds of inactivity will be slow (model reload). For benchmarks or back-to-back jobs, keep traffic flowing or set `AUDIOLLA_PRELOAD` server-side.
- **Don't poll `/api/ps`** as a load-progress indicator — it tells you what's loaded right now, not what's being loaded.
- **Output format on the response** comes from the `output_format` form field, NOT the upload's file extension. The server transcodes via ffmpeg.
- **Input format is auto-detected by ffmpeg** — WAV, MP3, FLAC, OGG, M4A, AAC, OPUS, etc. all work as input.
- **The `transform` `pitch` op takes semitones**, not cents — `n_semitones: 0.5` = half a semitone up, not a tiny shift.
- **`POST /v1/audio/loudness` with `target_lufs` returns audio**, not JSON. The original measurement comes back in the `X-Loudness-LUFS` response header. Use `-D headers.txt` with curl to capture it.

## Tips

- Use `GET /v1/engines` once at the start of a session to see what's actually configured — `AUDIOLLA_ENABLED_ENGINES` can hide things.
- For a multi-step pipeline (e.g. separate → master each stem → analyze), upload to `/v1/files` once and reference via the MCP tools instead of re-uploading via REST every time.
- Large input files: respect `AUDIOLLA_MAX_UPLOAD_BYTES` (default 200 MB). If unsure, `GET /healthz` first to confirm the server is up and ask the user to confirm the cap.
- Long-running separations (`htdemucs_ft` on CPU especially) can take minutes — set a generous curl `--max-time` and warn the user.
- If you need exact reproducibility between runs, pin the engine version by passing the explicit slug (`htdemucs` vs `htdemucs_ft`) — there is no "auto" mode for separation.
