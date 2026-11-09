# Engine and image rules

Prefix: ENG.

Engines are built by `build_engines()` in `src/audiolla/engines/__init__.py` from the registry `config.load_registry()` returns. The CUDA image copies `engines.json` to `/app/engines.json`; the CPU image copies `engines-cpu.json` there.

## Registries

- **ENG1:** Every slug lives in `engines.json`. Add it to `engines-cpu.json` too only if it runs acceptably on CPU; the CPU registry deliberately leaves out `htdemucs_ft`, `htdemucs_6s`, `mdx_extra` and the five generators. An entry present in both files keeps the same fields, except the CPU `htdemucs` description that warns it is slow.
- **ENG2:** An engine that must not run without a GPU gets `"cuda_only": true`. Only `/v1/audio/separate` enforces the flag today (`_validate_engine_supports_device` in `server.py`); a new heavy endpoint that needs a GPU calls it too. Generators fall back to CPU at fp32 (`_resolve_device` in `engines/music_gen.py`).
- **ENG3:** A new executor name goes into `_VALID_EXECUTORS` in `src/audiolla/config.py` and gets a branch in `build_engines()`. `load_registry()` rejects unknown executors at import, so a typo in either registry stops the whole server.
- **ENG4:** Each engine module defines one `EngineBase` subclass that overrides `_load_sync()` (returns the model, or `None` when there are no weights) and `_release_model()` as needed, and exposes its capability as a method that a predicate in `engines/__init__.py` detects (`is_separation_engine` checks `separate`, `is_music_gen_engine` checks `generate`). Handlers find engines by slug (`ENGINES.get("<slug>")`) or by predicate, never by class.
- **ENG5:** Engines that hold large models are loaded behind `EngineBase._lock` and touched (`_touch()`) before use, so the idle sweeper cannot unload them mid-call. Heavy endpoints call `await _evict_siblings(slug)` before running (separate, master, to_midi, enhance, generate, remix); a new endpoint backed by a GPU-sized model does the same.
- **ENG6:** Weights are downloaded at runtime, never committed and never baked into an image: Demucs by `entrypoint.sh` for entries with `"prefetch": "demucs"`, into `TORCH_HOME=/data/torch_cache`; UVR by audio-separator into `AUDIOLLA_UVR_MODELS_DIR`; Hugging Face models into `HF_HOME=/data/hf`. `.gitignore` and `.dockerignore` exclude weight file types and `/models/`; keep it that way.
- **ENG7:** Non-commercial model weights stay behind an explicit operator opt-in (`noncommercial: true` plus the `AUDIOLLA_ENABLE_NONCOMMERCIAL` check in `_require_noncommercial_optin` in `engines/music_gen.py`). A new license-encumbered model follows the same pattern and records its `license` in the registry.
- **ENG8:** A change to the engine set updates the counts and lists that mention it: the README tagline and table, `docs/engines.md` (engine list, endpoint table, registry fields), `docs/deployment.md` and `docs/index.md` image tables, the catalog entries in `_CATALOG_GROUPS`, and the skill (DOC2).

## Images and dependencies

- **ENG9:** Both images build on Torchbase pinned by digest (`TORCHBASE_IMAGE` in each Dockerfile and `TORCHBASE_*_IMAGE` in the `Makefile`) and assert the Torch version after installing (`2.5.1+cpu`, `2.5.1+cu124`). Changing Torch means changing the base image, both asserts and `tests/image_smoke.py`.
- **ENG10:** Light runtime dependencies go through `pyproject.toml` and `uv.lock` with the `make pkg-*` targets, which move `[tool.uv] exclude-newer` to seven days ago first (`scripts/bump_exclude_newer.sh`). Never edit `uv.lock` by hand or move the cutoff forward to today.
- **ENG11:** The ML stack goes into `scripts/heavy-deps-cpu.in` and `scripts/heavy-deps-cuda.in`, compiled with `make pkg-compile-heavy` into the hash-locked `requirements-heavy-*.txt`, which the Dockerfiles install with `--require-hashes`. Never hand-edit the compiled files. The numpy override in both Dockerfiles exists because deepfilternet declares `numpy<2.0`; keep it.
- **ENG12:** `Dockerfile.dev` pins its own copies of the web stack (FastAPI, uvicorn, pydantic, httpx, mcp, mido) and no ML libraries. When a light dependency version changes in `pyproject.toml`, change it there too.
- **ENG13:** Application source is copied after the dependency layers, so editing Python does not rebuild Torch layers. Keep new `COPY` lines for source after the dependency `RUN` steps.
