PORT ?= 8000

DEV_IMAGE  := psyb0t/audiolla-dev:latest
CPU_IMAGE  := psyb0t/audiolla:local
CUDA_IMAGE := psyb0t/audiolla:local-cuda

PYPROJECT := pyproject.toml
BUMP_HOST := bash scripts/bump_exclude_newer.sh $(PYPROJECT)

UID := $(shell id -u)
GID := $(shell id -g)

# Sandboxed dev container — all dev-side commands run inside this so the host
# stays clean. Heavy ML deps (demucs, matchering, etc.) live ONLY in the prod
# images. Unit tests stub the engine backends.
DEV_RUN := docker run --rm \
	-u $(UID):$(GID) \
	-e HOME=/tmp \
	-v $(PWD):/work \
	-w /work \
	$(DEV_IMAGE)

DEV_RUN_TTY := docker run --rm -it \
	-u $(UID):$(GID) \
	-e HOME=/tmp \
	-v $(PWD):/work \
	-w /work \
	$(DEV_IMAGE)

.PHONY: help dev-image shell \
        build build-cuda build-all \
        run run-cuda \
        test test-unit test-integration \
        lint format check clean \
        generate \
        pkg-lock pkg-upgrade pkg-add pkg-remove pkg-update pkg-compile-heavy

help: ## Show this help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

# -----------------------------------------------------------------------------
# Dev container — every other target depends on this.
# -----------------------------------------------------------------------------

dev-image: ## Build/refresh the sandboxed dev image
	docker build -f Dockerfile.dev -t $(DEV_IMAGE) .

shell: dev-image ## Drop into a shell inside the dev container
	$(DEV_RUN_TTY) bash

# -----------------------------------------------------------------------------
# Package management — uv inside the dev container.
# Every mutation bumps [tool.uv] exclude-newer to today first so the
# supply-chain age gate is always anchored to the moment of the change.
# -----------------------------------------------------------------------------

pkg-lock: dev-image ## Refresh uv.lock (honors current exclude-newer)
	$(DEV_RUN) uv lock

pkg-upgrade: dev-image ## Bump exclude-newer + refresh lock with newest pins
	$(BUMP_HOST)
	$(DEV_RUN) uv lock --upgrade

pkg-add: dev-image ## Add a package (usage: make pkg-add PKG=name[==ver])
	@test -n "$(PKG)" || (echo "usage: make pkg-add PKG=name[==ver]" >&2; exit 1)
	$(BUMP_HOST)
	$(DEV_RUN) uv add --no-sync $(PKG)

pkg-remove: dev-image ## Remove a package (usage: make pkg-remove PKG=name)
	@test -n "$(PKG)" || (echo "usage: make pkg-remove PKG=name" >&2; exit 1)
	$(BUMP_HOST)
	$(DEV_RUN) uv remove --no-sync $(PKG)

pkg-update: dev-image ## Upgrade ONE package (usage: make pkg-update PKG=name)
	@test -n "$(PKG)" || (echo "usage: make pkg-update PKG=name" >&2; exit 1)
	$(BUMP_HOST)
	$(DEV_RUN) uv lock --upgrade-package $(PKG)

# Heavy ML/DSP stack used by the prod images is NOT part of the uv.lock
# resolution (different torch flavor per variant, fetched from the pytorch
# index). It lives in scripts/heavy-deps-{cpu,cuda}.in and is compiled to
# hash-locked requirements-heavy-{cpu,cuda}.txt — both committed and
# consumed by Dockerfile / Dockerfile.cuda via `uv pip install
# --require-hashes`. Re-run this after editing the .in files.
pkg-compile-heavy: dev-image ## Re-compile hash-locked requirements-heavy-{cpu,cuda}.txt
	$(BUMP_HOST)
	$(DEV_RUN) bash scripts/compile_heavy_deps.sh

# -----------------------------------------------------------------------------
# Production image builds.
# -----------------------------------------------------------------------------

build: ## Build the CPU production image
	docker build -f Dockerfile -t $(CPU_IMAGE) .

build-cuda: ## Build the CUDA production image
	docker build -f Dockerfile.cuda -t $(CUDA_IMAGE) .

build-all: build build-cuda ## Build both production images

# -----------------------------------------------------------------------------
# Local run targets.
# -----------------------------------------------------------------------------

run: build ## Run CPU image locally (uses ~/.audiolla-data for models + files)
	mkdir -p $$HOME/.audiolla-data
	docker run --rm -it \
		-v $$HOME/.audiolla-data:/data \
		-e AUDIOLLA_DEVICE=cpu \
		-e HF_HUB_OFFLINE=0 \
		-p $(PORT):8000 \
		$(CPU_IMAGE)

run-cuda: build-cuda ## Run CUDA image locally (requires --gpus all support)
	mkdir -p $$HOME/.audiolla-data
	docker run --rm -it --gpus all \
		-v $$HOME/.audiolla-data:/data \
		-e AUDIOLLA_DEVICE=cuda \
		-e HF_HUB_OFFLINE=0 \
		-p $(PORT):8000 \
		$(CUDA_IMAGE)

# -----------------------------------------------------------------------------
# Test / lint / format — all inside the dev container.
# -----------------------------------------------------------------------------

test: test-unit ## Run unit tests (fast, offline, no GPU)

test-unit: dev-image ## Run unit tests in the dev container with coverage
	$(DEV_RUN) pytest tests/ -v \
		--cov=src/audiolla \
		--cov-report=term-missing:skip-covered

# Stricter gate: fail if line coverage on the support modules drops below
# 80%. Engine bodies (`_separate_sync` / `_master_sync` / etc.) are NOT in
# this gate because they all import heavy ML libs (demucs, librosa,
# matchering, pedalboard, sox, torch) lazily and those libs aren't in the
# dev image — the dev image is intentionally lightweight. The integration
# suite under `tests/integration/` covers the engine inference paths
# end-to-end against the prod image. This gate covers the glue code.
test-unit-cov-gate: dev-image ## Enforce ≥80% line coverage on support modules
	$(DEV_RUN) pytest tests/ \
		--cov=audiolla.audio \
		--cov=audiolla.auth \
		--cov=audiolla.files \
		--cov=audiolla.config \
		--cov=audiolla.engines.base \
		--cov-fail-under=80

# Integration suite — runs on the host (NOT inside the dev container) because
# it spawns sibling docker containers and pokes the audiolla HTTP port directly.
# The pytest session-scoped fixture (tests/integration/conftest.py) builds the
# CPU image first unless HARNESS_SKIP_BUILD=1, computes the union of engines
# needed by collected tests, spawns ONE container, and tears it down at
# session end (with atexit + SIGINT/SIGTERM/SIGHUP guards for interrupted
# sessions).
#
# Markers + env knobs:
#   HARNESS_GPU=1                              run CUDA tests (gpu marker)
#   HARNESS_IMAGE=psyb0t/audiolla:local-cuda   override the docker image
#   HF_TOKEN / HUGGINGFACE_TOKEN               unlock hf_gated tests
#   AUDIOLLA_ENABLE_NONCOMMERCIAL=1            unlock noncommercial (MusicGen)
#   HARNESS_KEEP=1                             leave container running on exit
#   HARNESS_SKIP_BUILD=1                       skip `make build` preflight
#
# Run subsets via pytest's own selection: `pytest tests/integration/ -k generate`,
# `pytest tests/integration/test_audio_enhance_deepfilter.py`, etc.
test-integration: ## Run integration tests (host-side; spawns docker containers via pytest)
	@pytest tests/integration/ -v

lint: dev-image ## Lint python sources
	$(DEV_RUN) flake8 src
	$(DEV_RUN) mypy src

format: dev-image ## Format python sources
	$(DEV_RUN) isort src
	$(DEV_RUN) black src

check: lint test ## Lint + unit tests

# -----------------------------------------------------------------------------
# Code generation — Pydantic schema from the OpenAPI source-of-truth.
# Re-run after every change to openapi.yaml. Generated files live in
# src/audiolla/schema/ and ARE committed to the repo (not built on container
# startup) so prod images don't need datamodel-codegen installed.
# -----------------------------------------------------------------------------

generate: dev-image ## Regenerate src/audiolla/schema/ from openapi.yaml
	$(DEV_RUN) bash scripts/generate_models.sh

clean: ## Remove build / cache artifacts (host-side)
	docker rmi $(CPU_IMAGE) $(CUDA_IMAGE) 2>/dev/null || true
	rm -rf build dist *.egg-info .pytest_cache .mypy_cache .ruff_cache .venv
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
