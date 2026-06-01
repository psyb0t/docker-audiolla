#!/usr/bin/env bash
# Compile hash-locked requirements files for the heavy ML/DSP stack used by
# the prod images. Two variants — CPU (torch+cpu) and CUDA (torch from cu126).
#
# Supply-chain gate: HEAVY_EXCLUDE_NEWER pins the maximum upload date for
# dependency resolution. Bump this manually when intentionally upgrading
# heavy-stack packages. It is set ahead of pyproject.toml's exclude-newer
# because several PyTorch-ecosystem packages (numpy, sympy) have missing
# upload-time metadata in PyPI, which uv ≥0.11 rejects when the cutoff is
# set to today's date.  Hash verification (--generate-hashes) is the primary
# supply-chain protection here; the date gate is a secondary layer.
#
# Generated files are committed; Dockerfiles install via
# `uv pip install --require-hashes -r requirements-heavy-<variant>.txt`.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PYTHON_VERSION=3.12
# Bump when intentionally adding/upgrading heavy-stack deps.
HEAVY_EXCLUDE_NEWER="2026-12-31T00:00:00Z"

compile_variant() {
    local variant="$1"
    local extra_index="$2"
    local in_src="${PROJECT_ROOT}/scripts/heavy-deps-${variant}.in"
    local out_file="${PROJECT_ROOT}/requirements-heavy-${variant}.txt"

    echo ">> compiling ${variant} -> ${out_file}"
    # uv resolves [tool.uv].exclude-newer from the *input file's* directory
    # tree, not just cwd.  Copying the .in file to /tmp keeps it out of the
    # project tree so HEAVY_EXCLUDE_NEWER takes effect uncontested.
    # uv also resolves [tool.uv].exclude-newer from the *output file's*
    # directory tree.  Write to a /tmp output too, then move into place.
    local tmp_in tmp_out
    tmp_in="$(mktemp /tmp/heavy-deps-${variant}-XXXXX.in)"
    tmp_out="$(mktemp /tmp/heavy-deps-${variant}-out-XXXXX.txt)"
    cp "${in_src}" "${tmp_in}"
    (
        cd /tmp
        UV_EXCLUDE_NEWER="${HEAVY_EXCLUDE_NEWER}" uv pip compile \
            --python-version "${PYTHON_VERSION}" \
            --generate-hashes \
            --extra-index-url "${extra_index}" \
            --index-strategy unsafe-best-match \
            --output-file "${tmp_out}" \
            "${tmp_in}"
    )
    mv "${tmp_out}" "${out_file}"
    rm -f "${tmp_in}"
}

compile_variant cpu  "https://download.pytorch.org/whl/cpu"
compile_variant cuda "https://download.pytorch.org/whl/cu126"

echo
echo "Done. Commit:"
echo "  ${PROJECT_ROOT}/requirements-heavy-cpu.txt"
echo "  ${PROJECT_ROOT}/requirements-heavy-cuda.txt"
