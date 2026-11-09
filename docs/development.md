---
title: "Development"
description: "Build, lint and test audiolla: Makefile targets, the dev container, spec-first code generation, dependency locks, CI, releases and the docs build."
nav_order: 23
---

# Development

Everything runs through `make`, and almost everything runs inside a throwaway dev container, so the host needs only Docker, make and git. `make help` lists every target.

## Layout

| Path | What |
| --- | --- |
| [src/audiolla/](https://github.com/psyb0t/docker-audiolla/tree/main/src/audiolla) | The server: `server.py` (routes), `mcp_server.py` (MCP tools), `engines/`, `audio.py`, `schema/` and the support modules described in [architecture](architecture.md). |
| [openapi.yaml](https://github.com/psyb0t/docker-audiolla/blob/main/openapi.yaml) | The REST API contract. |
| [engines.json](https://github.com/psyb0t/docker-audiolla/blob/main/engines.json), [engines-cpu.json](https://github.com/psyb0t/docker-audiolla/blob/main/engines-cpu.json) | Engine registries for the CUDA and CPU images. |
| [presets/](https://github.com/psyb0t/docker-audiolla/tree/main/presets) | Shipped preset workflows. |
| [tests/](https://github.com/psyb0t/docker-audiolla/tree/main/tests) | Offline unit tests, `image_smoke.py`, and the Docker-based `integration/` suite. |
| [scripts/](https://github.com/psyb0t/docker-audiolla/tree/main/scripts) | Model generation, dependency lock compilation and the `exclude-newer` bump. |
| `Dockerfile`, `Dockerfile.cuda`, `Dockerfile.dev` | CPU image, CUDA image, and the light dev image the Makefile runs tools in. |
| [docs/](https://github.com/psyb0t/docker-audiolla/tree/main/docs) | This site. |

## Everyday commands

```bash
make dev-image   # build the dev container (Python 3.12, uv, flake8, black, isort, mypy, pytest)
make shell       # interactive shell in it
make lint        # flake8 src, then mypy src
make format      # isort src, then black src
make test        # unit tests (same as make test-unit)
make check       # lint, then test
```

The dev image has the web stack (FastAPI, uvicorn, pydantic, httpx, mcp) but none of the ML libraries. Unit tests replace engines with mocks and never download a model, so they run offline and without a GPU.

## Tests

| Target | What it runs | Needs |
| --- | --- | --- |
| `make test-unit` | `pytest tests/ --ignore=tests/integration` with coverage | Docker |
| `make test-unit-cov-gate` | The same, failing under 80% line coverage on `audio`, `auth`, `files`, `config` and `engines.base` | Docker |
| `make test-retention` | File retention and config tests with a 90% coverage gate on `file_retention` | Docker |
| `make test-image` | `tests/image_smoke.py` inside the built CPU image: real Torch tensors, DSP, jobs and cleanup. `DEVICE=cuda` runs it in the CUDA image. | `make build` first; a GPU for CUDA |
| `make test-integration` | `pytest tests/integration/` on the host. It builds the CPU image, starts one container with the engines the selected tests need, and calls the real API. | Python with pytest on the host, Docker, disk for models |

The integration suite reads these variables: `HARNESS_GPU=1` for the CUDA tests, `HARNESS_IMAGE` to pick an image, `HF_TOKEN` or `HUGGINGFACE_TOKEN` for gated models, `AUDIOLLA_ENABLE_NONCOMMERCIAL=1` for MusicGen, `HARNESS_KEEP=1` to leave the container running and `HARNESS_SKIP_BUILD=1` to skip the build. Select tests with pytest's own options, for example `pytest tests/integration/ -k generate` or `-m "not gpu"`. Model downloads are cached in `.e2e-cache/`.

## Changing the API

The REST contract is [openapi.yaml](https://github.com/psyb0t/docker-audiolla/blob/main/openapi.yaml). Request and response models are generated from it, never written by hand:

1. Edit the path and its schemas in `openapi.yaml`, reusing shared components such as `BaseAudioInputRequest` and `BaseAudioOutputRequest` with `$ref`.
2. Run `make generate`. It runs `scripts/generate_models.sh` (datamodel-code-generator) in the dev container and rewrites `src/audiolla/schema/_generated.py`.
3. Write the handler in `src/audiolla/server.py`, taking the generated model from `audiolla.schema` as its one body parameter.
4. Commit `openapi.yaml` and the regenerated `_generated.py` together.

`src/audiolla/schema/__init__.py` is hand-written: it re-exports the generated classes, turns type aliases the generator emits into real subclasses, and holds the either-or validators (`validate_input_xor`, `validate_output_xor`). The server serves `openapi.yaml` at `/openapi.json`, so the spec you edit is the spec clients see.

## Dependencies

There are two dependency sets, both hash-locked:

- **Light runtime dependencies** (FastAPI, uvicorn, pydantic, httpx, mcp, mido, mutagen) are in `pyproject.toml` and `uv.lock`. The images install them with `uv export --frozen` and `uv pip install --require-hashes`, so a stale lock fails the build.
- **The ML and DSP stack** (Torch, Demucs, matchering, pedalboard, librosa and the rest) is specified in `scripts/heavy-deps-cpu.in` and `scripts/heavy-deps-cuda.in` and compiled to `requirements-heavy-cpu.txt` and `requirements-heavy-cuda.txt`, because the Torch wheels differ per image.

```bash
make pkg-lock                        # refresh uv.lock at the current cutoff
make pkg-add PKG=name==1.2.3         # add a dependency
make pkg-update PKG=name             # upgrade one dependency
make pkg-upgrade                     # upgrade everything
make pkg-remove PKG=name             # remove a dependency
make pkg-compile-heavy               # recompile both heavy locks, keeping versions
make pkg-compile-heavy VARIANT=cuda  # recompile only the CUDA lock
```

`pkg-add`, `pkg-remove`, `pkg-update` and `pkg-upgrade` first move `[tool.uv] exclude-newer` in `pyproject.toml` to UTC midnight seven days ago, so no package version younger than a week gets in. The heavy locks use their own cutoff, `HEAVY_EXCLUDE_NEWER` in `scripts/compile_heavy_deps.sh`, and keep existing pins. The dev image pins its own copies of the web stack in `Dockerfile.dev`, separate from `uv.lock`.

## Images

```bash
make build       # CPU image: psyb0t/audiolla:local, :v<version>, :latest
make build-cuda  # CUDA image: psyb0t/audiolla:local-cuda, :v<version>-cuda, :latest-cuda
make build-all   # both
make version     # print v<version> from pyproject.toml
```

Both build on Torchbase images pinned by digest; override with `TORCHBASE_CPU_IMAGE` or `TORCHBASE_CUDA_IMAGE`. Application source is copied after the dependencies, so editing Python code does not reinstall Torch. The Docker build context leaves out `docs/`, `tests/`, `scripts/`, `.agents/`, `README.md`, `Makefile` and `Dockerfile.dev`.

## CI and releases

[.github/workflows/pipeline.yml](https://github.com/psyb0t/docker-audiolla/blob/main/.github/workflows/pipeline.yml) runs on every push:

- every branch: `make lint`, `make test`, and `make generate`, which fails the run if the committed `src/audiolla/schema/_generated.py` does not match `openapi.yaml`;
- `main`: also builds both images, scans them with Grype, and pushes `:latest`, `:latest-cuda`, `:sha-<commit>` and `:sha-<commit>-cuda`;
- a `v*` tag: waits for that commit's `main` run to pass, re-tags the same image digests as `vX.Y.Z` and `vX.Y.Z-cuda` without rebuilding, creates the GitHub release, then publishes the skill and plugin to ClawHub and `server.json` to the MCP Registry.

The version lives in `pyproject.toml`. The [CHANGELOG](https://github.com/psyb0t/docker-audiolla/blob/main/CHANGELOG.md) states the versioning policy.

## Docs

This site is built by GitHub Pages from `docs/` on `main`. Build it locally with the same Jekyll image:

```bash
make docs   # output in .testing/docs-site
```
