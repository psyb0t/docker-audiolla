#!/usr/bin/env bash
# Compile hash-locked requirements files for the heavy ML/DSP stack used by
# the prod images. CPU and cu124 wheels match the inherited Torchbase stack.
#
# Supply-chain gate: HEAVY_EXCLUDE_NEWER pins the maximum upload date for
# dependency resolution. Bump this manually when intentionally upgrading
# heavy-stack packages. Existing output pins constrain resolution so changing
# a wheel flavor does not silently upgrade unrelated dependencies.
#
# Generated files are committed; Dockerfiles install via
# `uv pip install --require-hashes -r requirements-heavy-<variant>.txt`.
set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

PYTHON_VERSION=3.12
# Bump when intentionally adding/upgrading heavy-stack deps.
HEAVY_EXCLUDE_NEWER="2026-09-26T00:00:00Z"

compile_variant() {
	local variant="$1"
	local torch_backend="$2"
	local in_src="${PROJECT_ROOT}/scripts/heavy-deps-${variant}.in"
	local out_file="${PROJECT_ROOT}/requirements-heavy-${variant}.txt"

	echo ">> compiling ${variant} -> ${out_file}"
	# uv resolves [tool.uv].exclude-newer from the *input file's* directory
	# tree, not just cwd.  Copying the .in file to /tmp keeps it out of the
	# project tree so HEAVY_EXCLUDE_NEWER takes effect uncontested.
	# uv also resolves [tool.uv].exclude-newer from the *output file's*
	# directory tree.  Write to a /tmp output too, then move into place.
	local tmp_in tmp_out tmp_override
	tmp_in="$(mktemp "/tmp/heavy-deps-${variant}-XXXXX.in")"
	tmp_out="$(mktemp "/tmp/heavy-deps-${variant}-out-XXXXX.txt")"
	tmp_override="$(mktemp /tmp/heavy-deps-override-XXXXX.txt)"
	cp "${in_src}" "${tmp_in}"
	cp "${PROJECT_ROOT}/scripts/heavy-deps-overrides.txt" "${tmp_override}"
	(
		cd /tmp
		UV_EXCLUDE_NEWER="${HEAVY_EXCLUDE_NEWER}" uv pip compile \
			--python-version "${PYTHON_VERSION}" \
			--generate-hashes \
			--torch-backend "${torch_backend}" \
			--constraint "${out_file}" \
			--override "${tmp_override}" \
			--output-file "${tmp_out}" \
			"${tmp_in}"
	)
	mv "${tmp_out}" "${out_file}"
	rm -f "${tmp_in}" "${tmp_override}"
}

case "${1:-all}" in
cpu) compile_variant cpu cpu ;;
cuda) compile_variant cuda cu124 ;;
all)
	compile_variant cpu cpu
	compile_variant cuda cu124
	;;
*)
	echo 'usage: compile_heavy_deps.sh [cpu|cuda|all]' >&2
	exit 2
	;;
esac

echo
echo "Done. Commit:"
echo "  ${PROJECT_ROOT}/requirements-heavy-cpu.txt"
echo "  ${PROJECT_ROOT}/requirements-heavy-cuda.txt"
