# Changelog

## v0.1.0 — 2026-05-30

Initial release.

- `POST /v1/audio/separate` — Demucs stem separation (htdemucs, htdemucs_ft, htdemucs_6s, mdx_extra)
- `POST /v1/audio/master` — matchering reference-based mastering + pedalboard preset chain
- `POST /v1/audio/analyze` — librosa MIR analysis (BPM, key, loudness, duration, spectral features)
- `POST /v1/audio/transform` — pysox DSP chain (gain, EQ, compressor, reverb, pitch, tempo)
- `POST /v1/audio/loudness` — pyloudnorm LUFS measurement + normalization
- `GET /v1/engines` — list configured engines
- `GET /healthz`, `GET /api/ps`, `DELETE /api/ps/{engine}`, `POST /unload`
- `POST /v1/files`, `GET /v1/files/{path}` — server-side file staging
- CPU image (python:3.12-slim) + CUDA image (nvidia/cuda:12.6.3)
- OpenAPI 3.1 spec as the single source of truth for the wire shape
