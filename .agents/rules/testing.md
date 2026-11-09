# Testing rules

Prefix: TST.

How to run each layer: the Dev workflow table in [AGENTS.md](../../AGENTS.md#dev-workflow) and [docs/development.md](../../docs/development.md#tests).

## What every change needs

- **TST1:** `make check` (lint plus unit tests in the dev container) passes on the lines you changed before a change is called done. CI runs `make lint` and `make test` on every push through `.github/workflows/pipeline.yml`, and the image build waits for them.
- **TST2:** New behaviour gets unit tests in the same change, in `tests/test_<module or engine>.py` (`test_files.py`, `test_fetch.py`, `test_uvr_separator.py`, `test_server_new_endpoints.py` for routes), named after the behaviour they pin. Use `pytest.mark.parametrize` for input tables. `asyncio_mode = "auto"` is set in `pyproject.toml`, so `async def` tests need no decorator.

## Unit tests (`tests/`, `make test-unit`)

- **TST3:** Unit tests run offline in the dev image, which has no ML stack. Never import torch, librosa, demucs or another heavy library at test module level and never download a model. Engine modules import their libraries inside `_load_sync` or the `_*_sync` methods, so tests patch those methods or the engine object. Route tests patch `audiolla.server.ENGINES` with `MagicMock` engines (`AsyncMock` for capability methods) and `audiolla.server.MCP_SERVER` with a stub whose `session_manager.run` is a no-op async context manager, then drive the app with `fastapi.testclient.TestClient` (`tests/test_server_new_endpoints.py`).
- **TST4:** Settings are tested by reloading `audiolla.config` under a patched environment: set variables with `monkeypatch`, pop `audiolla.config` from `sys.modules` and import it again (`_reload_config` in `tests/test_config.py`). A new setting gets cases for its default, its accepted values and its rejected values. `tests/conftest.py` points `AUDIOLLA_ENGINES_FILE` at the repo's `engines.json` so `server.py` imports.
- **TST5:** Coverage gates are part of the contract: `make test-unit-cov-gate` (80% on `audio`, `auth`, `files`, `config`, `engines.base`) and `make test-retention` (90% on `file_retention`). Do not lower a threshold to make a change pass.

## Image and integration tests

- **TST6:** `tests/image_smoke.py` (`make test-image`) runs inside the built image with real Torch, DSP, jobs and retention. Run it after changing a Dockerfile, the dependency locks or the Torch version, on CPU and, when a GPU is available, with `DEVICE=cuda`.
- **TST7:** `tests/integration/` runs pytest on the host against one real container that `conftest.py` starts with `AUDIOLLA_ENABLED_ENGINES` set to the union of the collected tests' `@pytest.mark.engine("slug")` markers. Mark tests `gpu`, `hf_gated` or `noncommercial` when they need `HARNESS_GPU=1`, a Hugging Face token or `AUDIOLLA_ENABLE_NONCOMMERCIAL=1`; unmet markers skip. One file per endpoint or engine, named `test_<area>_<engine>.py` (`test_audio_separate_htdemucs.py`, `test_audio_generate_audioldm2.py`).
- **TST8:** Integration tests build images and download models; they are not part of `make check` or CI. When a change alters real inference, run the integration file that covers it and say in the change which tests ran and which could not (no GPU, no token).
- **TST9:** Integration fixtures are generated on each run by `_ensure_fixtures` (synthetic audio through the image's ffmpeg) into `tests/integration/.fixtures/`, which is gitignored except `.gitkeep`. Never commit audio fixtures.
