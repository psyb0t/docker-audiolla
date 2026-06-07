# Changelog

All notable changes per release. Versions follow [semver](https://semver.org)
pre-1.0 conventions: minor bumps may include breaking REST changes (called
out explicitly), patch bumps are docs / build / fixes only.

## v0.22.2 — 2026-06-07

Docs-only refresh of `.agents/.skills/audiolla/SKILL.md` — was a v0.1.0 artifact heavily drifted from the live API.

- Fixed 27+ stale endpoint paths (`/v1/audio/spectrogram`, `/v1/audio/dereverb`, `/v1/audio/visualize`, `/v1/audio/to_midi`, `/v1/audio/enhance`, `/v1/audio/loudness-curve`, `/v1/audio/hpss` — all moved to namespaced / engine-in-path routes since v0.1.0).
- Removed dead engine slug `uvr-deecho-aggressive` (consolidated into `uvr-deecho` with `aggressive=true` form param in v0.19.0).
- New sections: **Authoritative reference: `GET /v1/catalog`** (points agents at the live API catalog as source of truth), **Workflows — presets + ad-hoc pipelines**, **Async jobs**, **Output to presigned PUT URL**.
- Engines table expanded from ~15 → ~25 entries with correct backing routes.
- "When to use" / "When NOT to use" rewritten to cover ~30 newer capabilities + clarified the speech-features caveat (audiolla has VAD / diarization / DeepFilterNet — exclusion is transcription/ASR/TTS).
- Loudness gotcha rewritten — `/v1/audio/loudness` measures JSON-only, `/v1/audio/normalize` returns audio + LUFS headers.

## v0.22.1 — 2026-06-07

Positioning + MCP workflow tools.

- Unified all internal copy on **audio-production** (was drifting between "music-production" and "audio" — README was already correct).
- MCP: 5 new tools — `list_presets`, `describe_preset`, `list_ops`, `run_preset`, `run_pipeline_tool` — so LLM agents can reach the workflow surface that REST already had.
- Replaced hardcoded `"81 tools"` log line with the live count via `mcp.list_tools()`.

## v0.22.0 — 2026-06-07

Multiband compression + workflow primitives + big server refactor.

- New: `POST /v1/audio/multiband-compress` — N-band compressor with zero-phase LR4-equivalent crossovers (mastering-grade dynamics).
- New: `POST /v1/pipeline` — ad-hoc op chain run server-side; intermediates stay in memory between steps, no re-upload.
- New: `POST /v1/presets/{name}` + `GET /v1/presets[/{name}]` — curated YAML workflows. Shipped presets: `master-for-spotify` (3-band master + -14 LUFS), `podcast-cleanup` (DeepFilterNet + de-ess + -16 LUFS), `vocal-cleanup` (UVR dereverb + denoise + de-ess + light comp).
- New: `GET /v1/ops` (~24 pipeline op slugs) + `GET /v1/catalog` (17 categories, machine-readable endpoint list for discovery).
- `GET /v1/engines` now reports `loaded` + `idle_seconds` per engine.
- New env var: `AUDIOLLA_PRESETS_DIR` (default `/app/presets`).
- Internal refactor: `_run_with_optional_job()` + `_run_json_or_audio()` helpers — every audio-producing endpoint now flows through one well-typed helper. server.py shrinks ~900 lines.
- `audio.py` organised by section banner (CORE / TRANSFORM / STEREO / DYNAMICS / RESTORE / EFFECTS / ANALYZE / MIDI).
- mcp_server.py: new `_run_audio_tool()` helper.
- Fixed pre-existing flaky integration tests: loudness URL bug, UVR curl timeout, 400-vs-404 file-not-found mismatches in hpss/trim/mix.
- Tests: unit 280 → 304, integration 103/103 across refactored + new endpoints.

## v0.21.1 — 2026-06-04

Supply-chain age gate: 7-day floor on bump.

- `bump_exclude_newer.sh` emits `today_utc - 7 days` instead of today, so fresh wheels in the post-publish attack window are excluded from resolution until they've had a week of community scrutiny.
- README and inline docs updated to explain the 7-day floor.

## v0.21.0 — 2026-06-04

Async jobs support `output_url`.

- Pass `output_url=<presigned PUT URL>` to any `async_job=true` request and the result is PUT to the URL on completion instead of staged locally.
- Inline streaming is not supported for async jobs (deliberate).
- Priority order: `output_url` → `output_path` → auto-generated `jobs/{id}.{ext}` fallback.

## v0.20.0 — 2026-06-04

**Breaking.** Visualize endpoints split into image/ and video/ sub-namespaces.

- `/v1/audio/visualize/spectrogram` → `/v1/audio/visualize/image/spectrogram` (PNG, color + scale params).
- `/v1/audio/visualize/waveform` → `/v1/audio/visualize/image/waveform` (PNG, color param).
- `/v1/audio/visualize/{mode}` → `/v1/audio/visualize/video/{mode}` (MP4/WebM; `mode` is a URL path segment now, no longer a form field).
- Each variant takes only the params it actually needs — no more megaendpoint with ignored fields.

## v0.19.0 — 2026-06-04

**Breaking.** Endpoint consolidation + `uvr-deecho` aggressive mode.

- `/v1/audio/dereverb/{engine}` + `/v1/audio/deecho/{engine}` + `/v1/audio/denoise/{engine}` (UVR variants) → unified at `POST /v1/audio/restore/{engine}`.
- DSP noise reduction → `POST /v1/audio/noise-reduce/{engine}` (engine = `noise-reduce` for DSP, `uvr-denoise` for ML).
- `/v1/audio/spectrogram` → `/v1/audio/visualize/spectrogram` (first move under the visualize namespace).
- `/v1/audio/waveform` → `/v1/audio/visualize/waveform`.
- `/v1/audio/visualize` (mode in form field) → `/v1/audio/visualize/{mode}` (mode in URL path).
- `/v1/audio/hpss` → `/v1/audio/separate/hpss`.
- `/v1/audio/loudness-curve` → `/v1/audio/loudness/curve`.
- `/v1/audio/noise-reduce` → `/v1/audio/noise-reduce/{engine}` (engine in URL path).
- New: `aggressive=true` form param on `uvr-deecho` for hard echo removal (replaces the previous `uvr-deecho-aggressive` engine slug).

## v0.17.0 — 2026-06-04

De-ess, stereo-field, audio thumbnail, MIDI humanize.

- `POST /v1/audio/deess` — split-band de-esser, no engine required.
- `POST /v1/audio/stereo-field` — correlation / width / balance / mono-compat analysis.
- `POST /v1/audio/thumbnail` — onset-density preview clip extraction (requires `librosa-analyze`).
- `POST /v1/midi/humanize` — timing + velocity jitter with optional deterministic seed.
- MCP: 85 tools total.

## v0.16.0 — 2026-06-04

Six new features.

- `POST /v1/audio/loudness/curve` — RMS envelope over time.
- `POST /v1/audio/pitch-correct` — snap to nearest semitone (auto-tune).
- `POST /v1/audio/repair` — declip + dehum (50/60 Hz notch).
- `POST /v1/audio/loop-point` — find best seamless loop boundary.
- `POST /v1/midi/drum` — step-sequencer spec → GM drum MIDI.
- `POST /v1/audio/chords-to-midi` — chord detection → MIDI progression.

## v0.15.1 — 2026-06-04

README fully updated for v0.15.0 features.

## v0.15.0 — 2026-06-04

Async jobs + webhooks + 8 new endpoints + metadata engine.

- New: `async_job=true` form param on every audio-producing endpoint — fire-and-forget with optional `webhook_url` POST callback on completion.
- New: `/v1/jobs` (list), `/v1/jobs/{id}` (poll), `DELETE /v1/jobs/{id}` (cancel).
- New: `metadata` engine — read/write ID3, Vorbis, FLAC tags via mutagen.
- 8 new endpoints including audio metadata, clip-detect, mid-side, beat-slice, conv-reverb, transient.
- 40 new integration tests.

## v0.14.2 — 2026-06-03

bpm-match bug fix + test suite corrections.

- Fixed `beats_result["tempo"]` → `beats_result["tempo_bpm"]` KeyError crash.
- Zero-BPM guard: HTTP 400 when audio has no detectable beat.
- Test fixes: missing staged file returns 404 (not 400), bpm-match uses a real click-track fixture, DIND-safe fixture path.
- All 113 integration test cases pass.

## v0.14.1 — 2026-06-03

Integration tests for 15 endpoints added in v0.12.0–v0.14.0. Each test boots its own ephemeral container.

## v0.14.0 — 2026-06-03

Five new editing primitives.

- `POST /v1/audio/split` — equal-time (N parts) or silence-based split; ZIP output.
- `POST /v1/audio/pan` — stereo pan via ffmpeg pan filter; position [-1.0, 1.0].
- `POST /v1/audio/eq` — parametric EQ via ffmpeg equalizer chain; any number of bands.
- `POST /v1/audio/key-match` — detect source key (chord-detect) + pitch-shift to target key.
- `POST /v1/audio/sidechain-duck` — ffmpeg sidechaincompress; primary duck on trigger.
- MCP: 58 tools total.

## v0.13.0 — 2026-06-03

Five more editing primitives.

- `POST /v1/audio/fade` — ffmpeg afade with 13 curve shapes.
- `POST /v1/audio/reverse` — flip audio backwards.
- `POST /v1/audio/loop` — repeat N times (count >= 2).
- `POST /v1/audio/bpm-match` — auto-detect source BPM (librosa) then stretch to target BPM.
- `POST /v1/audio/stereo-width` — M/S processing; width 0.0=mono, 1.0=original, up to 3.0.
- MCP: 53 tools total.

## v0.12.0 — 2026-06-03

- `POST /v1/audio/concat` — stitch N files end-to-end via ffmpeg concat filter.
- `POST /v1/audio/speed` — playback speed change without pitch shift (0.1–10×) via chained atempo filters.
- `POST /v1/audio/convert` — re-encode with target format, sample_rate, channels.
- `POST /v1/audio/similar` — CLAP cosine similarity between two audio files.
- `POST /v1/midi/quantize` — dedicated grid-snap endpoint.
- MCP: 48 tools total.

## v0.11.0 — 2026-06-03

- `POST /v1/audio/info` — ffprobe metadata (duration, codec, sample_rate, channels, bit_depth, format, bit_rate, frames).
- `POST /v1/audio/trim` — cut audio to `[start_sec, end_sec)`.
- `POST /v1/audio/mix` — N-track mix with per-track `gain_db` via ffmpeg amix.
- `POST /v1/audio/classify` — zero-shot classification via CLAP — accepts a JSON array of text labels, returns them ranked by cosine similarity.
- MCP: 43 tools total.

## v0.10.0 — 2026-06-03

HPSS, spectral noise reduction, loudness endpoint split.

- New engines: `hpss` (harmonic/percussive via librosa median filter), `noise-reduce` (stationary + non-stationary spectral reduction, no GPU).
- API split: `/v1/audio/loudness` is now JSON-only measurement; `/v1/audio/normalize` is the new normalization endpoint with required `target_lufs`.
- `POST /v1/audio/hpss` — ZIP with harmonic + percussive stems.
- `POST /v1/audio/noise-reduce` — denoised audio.
- MCP: 39 tools total.

## v0.9.0 — 2026-06-03

Stretch, audio tagging, CLAP embeddings.

- New engine: `stretch` — librosa phase vocoder, time-stretch + pitch-shift (`POST /v1/audio/stretch`).
- New engine: `ast-tag` — Audio Spectrogram Transformer; top-K AudioSet labels (`POST /v1/audio/tag`).
- New engine: `clap-embed` — LAION CLAP 512-dim L2-normalised audio embeddings; optional text-query cosine similarity (`POST /v1/audio/embed`).
- Bug fix: CPU Dockerfile now sets `HF_HOME=/data/hf` (tag/embed model cache was unreachable).
- 15 new integration tests.

## v0.8.0 — 2026-06-03

DeepFilterLib build fix + beat `start_bpm` + integration test buildout.

- Dockerfile CPU + CUDA: `deepfilterlib` now compiles from sdist via Rust/cargo; numpy override extracted with hashes so `--require-hashes` install succeeds.
- librosa beats: optional `start_bpm` seed parameter.
- 35 new/extended integration tests: fingerprint, MIR, visuals, MIDI utils, audio-to-MIDI, chords, diarize, VAD.

## v0.7.0 — 2026-06-02

Chord/key detect + VAD + speaker diarization + path-param engine routing.

- New engine: `chord-detect` — Krumhansl-Schmuckler + chroma template matching (`POST /v1/audio/chords`).
- New engine: `silero-vad` — voice activity detection (`POST /v1/audio/vad`).
- New engine: `pyannote` — speaker diarization (`POST /v1/audio/diarize`; requires `HUGGINGFACE_TOKEN`).
- Endpoint routing: engine moved from form param to URL path segment for several endpoints.

## v0.6.1 — 2026-06-02

Unit + integration tests for all new engines and endpoints (249 total).

## v0.6.0 — 2026-06-02

Polyphonic audio-to-MIDI + neural speech enhancement.

- New engine: `basic-pitch` — Spotify basic-pitch ONNX, polyphonic audio → MIDI (`POST /v1/audio/to_midi`).
- New engine: `deepfilter` — DeepFilterNet DF3 noise suppression (`POST /v1/audio/enhance`).

## v0.5.0 — 2026-06-02

AI audio restoration via UVR / audio-separator.

- New engines: `uvr-dereverb` (BS-Roformer SDR 19+), `uvr-deecho` (VR Architecture), `uvr-deecho-aggressive` (consolidated into `uvr-deecho` in v0.19.0), `uvr-denoise` (MelBand Roformer SDR 28), `uvr-karaoke`, `uvr-vocal-bsr`.
- Endpoints: `/v1/audio/dereverb`, `/v1/audio/deecho`, `/v1/audio/denoise` (all consolidated to `/v1/audio/restore/{engine}` in v0.19.0).

## v0.4.2 — 2026-06-01

Management endpoints moved to `/v1/ps` + `/v1/unload`; docs defaults clarified.

## v0.4.1 — 2026-06-01

README update for v0.4.0 features (docs only).

## v0.4.0 — 2026-06-01

MIR, silence detection, visualisations, fingerprinting, MIDI inspect/transform.

- 11 new REST endpoints + MCP tools across 5 new/extended engines.
- New: beat / onset / melody / segment analysis via `librosa-analyze`.
- New: silence detection + trimming.
- New: static PNG spectrogram/waveform + 8-mode animated MP4/WebM video (`ffmpeg-render`).
- New: Chromaprint acoustic fingerprinting (`audio-fingerprint`).
- New: MIDI inspection + transformation (transpose, quantize, tempo, channel filter).

## v0.3.1 — 2026-06-01

README accuracy fixes + project version metadata bump.

## v0.3.0 — 2026-05-31

Generic effects chain + MIDI compose/render.

- `POST /v1/audio/fx` — full pedalboard catalog (Compressor, Reverb, PitchShift, filters, …) as an ordered chain of `{type, params}`.
- `POST /v1/midi/compose` — JSON spec → SMF bytes (mido).
- `POST /v1/midi/render` — MIDI → audio via fluidsynth + FluidR3 GM SoundFont.
- `POST /v1/midi/generate` — compose + render in one call.

## v0.2.0 — 2026-05-31

`file_path` / `file_url` / `output_path` / `output_url` + SSRF-safe URL policy.

- Three input modes: multipart upload, staged file path, remote URL (allowlist/denylist via `AUDIOLLA_FETCH_MODE`).
- Three output modes: inline bytes, write to staging, PUT to presigned URL.
- File staging API: `GET/PUT/DELETE /v1/files`.

## v0.1.2 — 2026-05-31

README accuracy fixes + agent skill `.agents/.skills/audiolla/SKILL.md`.

## v0.1.0 — 2026-05-30

Initial release.

- `POST /v1/audio/separate` — Demucs stem separation (htdemucs, htdemucs_ft, htdemucs_6s, mdx_extra).
- `POST /v1/audio/master` — matchering reference-based mastering + pedalboard preset chain.
- `POST /v1/audio/analyze` — librosa MIR analysis (BPM, key, loudness, duration, spectral features).
- `POST /v1/audio/transform` — pysox DSP chain (gain, EQ, compressor, reverb, pitch, tempo).
- `POST /v1/audio/loudness` — pyloudnorm LUFS measurement + normalization (split into measure/normalize in v0.10.0).
- `GET /v1/engines` — list configured engines.
- `GET /healthz`, `GET /api/ps`, `DELETE /api/ps/{engine}`, `POST /unload` (moved to `/v1/ps` + `/v1/unload` in v0.4.2).
- `POST /v1/files`, `GET /v1/files/{path}` — server-side file staging.
- CPU image (python:3.12-slim) + CUDA image (nvidia/cuda:12.6.3).
- OpenAPI 3.1 spec as the single source of truth for the wire shape.
