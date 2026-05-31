---
name: audiolla
description: HTTP/MCP client for a user-deployed audiolla music-production server. Use ONLY when the user has explicitly named audiolla AND provided AUDIOLLA_URL (or has it set in the environment). Capabilities: stem separation (Demucs), mastering (matchering reference / pedalboard preset chain), MIR analysis (BPM, key, LUFS, spectral features via librosa), DSP transforms (gain, EQ, compand, reverb, pitch, tempo, etc. via SoX), loudness measurement and normalization, generic effects chains (full pedalboard catalog as ordered chain), and MIDI composition + rendering. The MIDI compose endpoint accepts a JSON song spec the agent writes itself (no AI runs server-side) and returns Standard MIDI File bytes; midi/render synthesises MIDI to audio via fluidsynth + a bundled General MIDI SoundFont; midi/generate chains both. Audio I/O supports three input modes (multipart upload, staged file path under /v1/files, or remote URL — only when the operator has enabled AUDIOLLA_FETCH_MODE) and three output modes (inline bytes, write to staging, PUT to presigned URL). Audiolla only fetches/uploads to URLs when the operator has explicitly enabled AUDIOLLA_FETCH_MODE — if a request returns "URL fetch/upload is disabled", do NOT try to bypass it. Do not use this skill for generic audio-processing questions or for users who haven't named audiolla.
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
| `fx-chain` | Arbitrary pedalboard chain | full pedalboard catalog as `[{type, params}, ...]` — backs `/v1/audio/fx`. VST3 / AU / external-plugin classes deliberately blocked |
| `midi-compose` | JSON → MIDI bytes | song-spec transcoder; no AI server-side, the agent writes the spec |
| `midi-render` | MIDI → audio | fluidsynth + FluidR3_GM SoundFont (GM patches 0-127, drum kit on channel 9) |

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

### Effects chain (`/v1/audio/fx`)

Arbitrary pedalboard effect chain — full catalog. Different from `/v1/audio/master` (which runs presets).

```bash
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/fx \
  -F "file=@track.wav" \
  -F 'effects=[
    {"type":"Compressor","params":{"threshold_db":-18,"ratio":4.0}},
    {"type":"Reverb","params":{"room_size":0.5,"wet_level":0.3}},
    {"type":"PitchShift","params":{"semitones":2}},
    {"type":"Gain","params":{"gain_db":-3}}
  ]' \
  -o out.wav
```

Allowed `type` values: `Compressor`, `Limiter`, `NoiseGate`, `Gain`, `Clipping`, `Distortion`, `Bitcrush`, `Reverb`, `Chorus`, `Delay`, `Phaser`, `PitchShift`, `HighShelfFilter`, `LowShelfFilter`, `PeakFilter`, `HighpassFilter`, `LowpassFilter`, `LadderFilter`, `IIRFilter`, `GSMFullRateCompressor`, `MP3Compressor`, `Resample`, `Invert`, `Convolution`.

`VST3Plugin`, `AudioUnitPlugin`, `ExternalPlugin` are deliberately blocked — they load arbitrary native code from arbitrary filesystem paths. Server returns 400 if asked.

### MIDI composition (`/v1/midi/compose`)

Transcode a JSON song spec to a Standard MIDI File. **No AI runs server-side** — your agent writes the spec, audiolla turns it into MIDI bytes.

```bash
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  -H 'Content-Type: application/json' \
  $AUDIOLLA_URL/v1/midi/compose \
  -d '{
    "tempo_bpm": 120,
    "time_signature": [4, 4],
    "key_signature": "C",
    "tracks": [
      {"name":"Lead","program":0,"channel":0,"notes":[
        {"pitch":60,"start_beats":0.0,"duration_beats":0.5,"velocity":100},
        {"pitch":64,"start_beats":0.5,"duration_beats":0.5,"velocity":100},
        {"pitch":67,"start_beats":1.0,"duration_beats":0.5,"velocity":100}
      ]},
      {"name":"Drums","program":0,"channel":9,"notes":[
        {"pitch":36,"start_beats":0.0,"duration_beats":0.1,"velocity":110}
      ]}
    ]
  }' \
  -o song.mid
```

Spec fields:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `tempo_bpm` | float | 120 | 1.0 ≤ bpm ≤ 999.0 |
| `time_signature` | `[num, den]` | `[4, 4]` | denominator must be 1/2/4/8/16/32 |
| `key_signature` | string | none | `"C"`, `"Am"`, `"F#"`, `"Bbm"` — letter [+ #/b] [+ m for minor] |
| `ticks_per_beat` | int | 480 | 24 ≤ tpb ≤ 1920 |
| `tracks[].name` | string | none | optional, writes a `track_name` meta event |
| `tracks[].program` | int 0-127 | 0 | General MIDI program (Acoustic Grand Piano = 0, Distortion Guitar = 30, Synth Brass 1 = 62, etc.) |
| `tracks[].channel` | int 0-15 | 0 | **Channel 9 is the GM drum channel** — pitch maps to drum kit, not piano |
| `tracks[].volume` | int 0-127 | 100 | MIDI CC#7 — initial volume |
| `tracks[].pan` | int 0-127 | 64 | MIDI CC#10 — initial pan (64 = centre) |
| `tracks[].notes[].pitch` | int 0-127 | required | 60 = middle C |
| `tracks[].notes[].start_beats` | float ≥ 0 | 0 | beat-based absolute position |
| `tracks[].notes[].duration_beats` | float > 0 | required | must be > 1/64 beat (≈ a 256th note) |
| `tracks[].notes[].velocity` | int 1-127 | 100 | |

GM drum kit reference for channel 9: 35 acoustic bass drum, 36 kick, 38 snare, 39 hand clap, 40 electric snare, 42 closed hi-hat, 46 open hi-hat, 49 crash, 51 ride, 57 crash 2.

Spec validation is fail-loud — bad pitch / negative duration / unknown program returns a 400 with the offending path in the message (e.g. `tracks[1].notes[3].pitch must be in [0, 127], got 200`).

Pass `?output_path=midi/song.mid` to stage the MIDI in `/v1/files` instead of getting bytes inline.

### MIDI rendering (`/v1/midi/render`)

Synthesise MIDI to audio via fluidsynth. Default SoundFont is FluidR3_GM (bundled in the prod image). Override per-request with a staged `.sf2`.

```bash
# Render a freshly-composed MIDI inline
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/midi/render \
  -F "file=@song.mid" \
  -F "output_format=wav" \
  -o song.wav

# Render with a custom SoundFont (must be staged first)
curl -X PUT -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/files/sf/orchestral.sf2 --data-binary @my.sf2
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/midi/render \
  -F "file_path=midi/song.mid" \
  -F "soundfont_path=sf/orchestral.sf2" \
  -F "output_format=flac" \
  -F "gain=0.3" \
  -F "samplerate=48000" \
  -o orch.flac
```

`gain` range `[0.0, 5.0]` — default `0.5` is calibrated to avoid clipping on percussive MIDI. `samplerate` must be 22050 / 44100 / 48000 / 88200 / 96000.

### MIDI generate (`/v1/midi/generate`)

One-shot compose + render. Body is the same JSON song spec as `/v1/midi/compose`; output is audio. Audio knobs (`output_format`, `soundfont_path`, `gain`, `samplerate`, `output_path`, `output_url`) go on the query string.

```bash
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  -H 'Content-Type: application/json' \
  "$AUDIOLLA_URL/v1/midi/generate?output_format=wav&output_path=songs/v1.wav" \
  -d @spec.json
```

### File staging

A simple server-side file store under `/v1/files`. Plain CRUD — upload, list, download, delete. Once a file is staged, every audio endpoint can reference it by relative path via the `file_path` form field (and the master endpoint accepts `reference_path` for the reference track).

```bash
# Upload (path can have subdirectories: bands/myband/track.wav)
curl -X PUT -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/files/mytrack.wav \
  --data-binary @track.wav

# Use the staged path on any audio call
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/separate \
  -F "file_path=mytrack.wav" \
  -F "engine=htdemucs" \
  -F "stems=vocals" \
  -o vocals.wav

# Process AND write the result back to staging in one call
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/separate \
  -F "file_path=mytrack.wav" \
  -F "engine=htdemucs" \
  -F "stems=vocals" \
  -F "output_path=stems/mytrack-vocals.wav"
# → {"path":"stems/mytrack-vocals.wav","size":...,"engine":"htdemucs","stem":"vocals","output_format":"wav"}

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

### Input and output modes (every audio endpoint)

Every audio endpoint accepts exactly one of three input forms — supplying zero or more than one returns 400:

- `file` — multipart upload (raw bytes in the request)
- `file_path` — relative path under the staging area (must exist, populated via PUT /v1/files)
- `file_url` — remote URL the server fetches (subject to the `AUDIOLLA_FETCH_MODE` policy — see below)

Audio-producing endpoints (separate, master, transform, loudness with target) also accept one of:

- `output_path` — server writes the result to `FILES_DIR / <path>`; response is JSON `{path, size, ...}`
- `output_url` — server PUTs the result to a presigned URL; response is JSON `{url, size, ...}`
- neither → response is audio bytes inline (default, backwards compatible)

`output_path` and `output_url` are mutually exclusive; both being set is 400.

The master endpoint additionally accepts `reference` / `reference_path` / `reference_url` for the reference track in `mode=reference` — same exactly-one-of rule.

### Remote URLs (file_url / output_url)

The server-side URL fetch is **disabled by default**. To enable it, the operator sets:

```
AUDIOLLA_FETCH_MODE = disabled | allowlist | denylist     (default: disabled)
AUDIOLLA_FETCH_HOSTS = comma-separated host patterns       (required when mode=allowlist)
AUDIOLLA_FETCH_SCHEMES = https,http                        (default: https only)
AUDIOLLA_FETCH_TIMEOUT = 30s                               (per fetch/upload)
AUDIOLLA_FETCH_ALLOW_PRIVATE = false                       (allow private/loopback IPs)
AUDIOLLA_FETCH_MAX_REDIRECTS = 5
```

Host patterns are exact match (`bucket.s3.amazonaws.com`) or single-wildcard subdomain (`*.s3.amazonaws.com`, matches any `<x>.s3.amazonaws.com` but NOT `s3.amazonaws.com` itself).

Always-on protections regardless of mode:
- DNS-resolved private / loopback / link-local / metadata-service IPs (`169.254.169.254`) rejected unless `AUDIOLLA_FETCH_ALLOW_PRIVATE=true`
- Only schemes in `AUDIOLLA_FETCH_SCHEMES` accepted; `file://`, `gopher://`, etc. always rejected
- Each redirect's `Location` re-validated through the full policy before following
- Body streamed; abort if it exceeds `AUDIOLLA_MAX_UPLOAD_BYTES`

If you're scripting and the server returns `URL fetch/upload is disabled` (400), tell the user — don't try to bypass it. The operator chose `disabled` for a reason.

Example — fetch from S3, master, PUT to a presigned URL:

```bash
curl -X POST -H "Authorization: Bearer $AUDIOLLA_TOKEN" \
  $AUDIOLLA_URL/v1/audio/master \
  -F "file_url=https://my-bucket.s3.amazonaws.com/track.wav" \
  -F "mode=chain" \
  -F "preset=loud" \
  -F "output_url=https://my-bucket.s3.amazonaws.com/mastered.wav?X-Amz-Signature=..."
# → {"url":"...","size":...,"engine":"pedalboard-chain","mode":"chain","output_format":"wav"}
```

## MCP

audiolla exposes a Model Context Protocol server at `/v1/mcp` using the streamable HTTP transport. Same auth as REST — pass `Authorization: Bearer $AUDIOLLA_TOKEN`.

Each audio tool accepts exactly one of `file_path` or `file_url` for input (same `AUDIOLLA_FETCH_MODE` policy as REST). For output, the audio tools default to base64-encoded bytes; pass `output_url` to PUT to a presigned URL instead (response then carries `url` + `size` instead of `audio_base64`). The `separate` tool takes `output_urls` as a per-stem dict when uploading each stem to its own presigned URL.

| Tool | Inputs | Output |
|------|--------|--------|
| `list_engines` | — | engine catalog with `loaded` flag |
| `separate` | `engine`, `stems`, `file_path` or `file_url`, optional `output_urls: {stem: url}` | base64 stems OR `{uploaded_stems: {stem: {url, size}}}` |
| `master` | `mode`, `file_path` or `file_url`, `reference_path` or `reference_url` (mode=reference), `preset` (mode=chain), `target_lufs`, `output_url` | base64 audio OR `{url, size}` |
| `analyze` | `file_path` or `file_url`, `features` | librosa feature dict |
| `transform` | `operations`, `file_path` or `file_url`, `output_url` | base64 audio OR `{url, size}` |
| `loudness` | `file_path` or `file_url`, `target_lufs`, `output_url` | measurement JSON or `{audio_base64 or url+size, measured_lufs, target_lufs, normalized}` |
| `fx` | `effects`, `file_path` or `file_url`, `output_format`, `output_url` | base64 audio OR `{url, size}` |
| `midi_compose` | `spec` (song JSON), `output_path`, `output_url` | `{midi_base64, size}` OR `{path, size}` OR `{url, size}` |
| `midi_render` | `file_path` or `file_url` (MIDI), `soundfont_path`, `gain`, `samplerate`, `output_format`, `output_url` | base64 audio OR `{url, size}` |
| `midi_generate` | `spec`, `soundfont_path`, `gain`, `samplerate`, `output_format`, `output_url` | base64 audio + `midi_size`, OR `{url, size, midi_size}` |
| `list_files` | — | `{files: [...]}` |
| `put_file` | `path`, `content_base64` | `{path, size}` |
| `get_file` | `path` | `{path, size, content_base64}` |
| `delete_file` | `path` | `{deleted}` |

Audio over MCP is base64-in / base64-out by default — JSON-RPC can't carry raw bytes. The two escape hatches are: stage the file ahead of time and pass `file_path` (small upload via `put_file` or out-of-band via REST PUT), or pass `file_url` / `output_url` so the server fetches/PUTs directly to S3-style storage. For large files always prefer one of those.

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
- **`POST /v1/audio/loudness` with `target_lufs` returns audio**, not JSON, in the default output mode. The measurement comes back in the `X-Loudness-LUFS` response header — use `-D headers.txt` with curl to capture it. If you set `output_path` or `output_url` the response IS JSON and `measured_lufs` is in the body instead.
- **`file_url` / `output_url` are disabled by default.** If the server returns `URL fetch/upload is disabled` (400), the operator hasn't enabled `AUDIOLLA_FETCH_MODE` — don't try to bypass it.
- **`output_path` and `output_url` are mutually exclusive.** Supplying both is 400. Supplying neither = default inline-bytes response.
- **`file`, `file_path`, `file_url` are mutually exclusive too.** Same exactly-one-of rule; zero or more-than-one is 400.

## Tips

- Use `GET /v1/engines` once at the start of a session to see what's actually configured — `AUDIOLLA_ENABLED_ENGINES` can hide things.
- For a multi-step pipeline (e.g. separate → master each stem → analyze), upload to `/v1/files` once and reference via `file_path` on every subsequent REST call (or the equivalent MCP tools) — no need to re-upload. Chain `output_path` into the next call's `file_path` to keep everything server-side until you actually need bytes.
- Large input files: respect `AUDIOLLA_MAX_UPLOAD_BYTES` (default 200 MB). If unsure, `GET /healthz` first to confirm the server is up and ask the user to confirm the cap.
- Long-running separations (`htdemucs_ft` on CPU especially) can take minutes — set a generous curl `--max-time` and warn the user.
- If you need exact reproducibility between runs, pin the engine version by passing the explicit slug (`htdemucs` vs `htdemucs_ft`) — there is no "auto" mode for separation.
