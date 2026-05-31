#!/usr/bin/env bash
# Compile hash-locked requirements files for the heavy ML/DSP stack used by
# the prod images. Two variants — CPU (torch+cpu) and CUDA (torch from cu126).
# Honors [tool.uv] exclude-newer from pyproject.toml.
#
# Generated files are committed; Dockerfiles install via
# `uv pip install --require-hashes -r requirements-heavy-<variant>.txt`.
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON_VERSION=3.12

compile_variant() {
    local variant="$1"
    local extra_index="$2"
    local in_file="scripts/heavy-deps-${variant}.in"
    local out_file="requirements-heavy-${variant}.txt"

    echo ">> compiling ${variant} -> ${out_file}"
    uv pip compile \
        --python-version "${PYTHON_VERSION}" \
        --generate-hashes \
        --extra-index-url "${extra_index}" \
        --index-strategy unsafe-best-match \
        --output-file "${out_file}" \
        "${in_file}"
}

compile_variant cpu  "https://download.pytorch.org/whl/cpu"
compile_variant cuda "https://download.pytorch.org/whl/cu126"

echo
echo "Done. Commit:"
echo "  ${PWD}/requirements-heavy-cpu.txt"
echo "  ${PWD}/requirements-heavy-cuda.txt"
