#!/bin/bash
# Regenerate src/audiolla/schema/_generated.py from openapi.yaml using
# datamodel-code-generator. The generated file is committed to the repo — it is
# NOT auto-generated at build time, so prod images don't need the generator.
#
# Run after every change to openapi.yaml. The hand-written `__init__.py`
# re-exports everything from `_generated.py` so callers do
# `from audiolla.schema import FooRequest` without caring about the split.
#
# Requires: pip install 'datamodel-code-generator[http]'
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

OPENAPI="${REPO_ROOT}/openapi.yaml"
OUT_FILE="${REPO_ROOT}/src/audiolla/schema/_generated.py"

if ! command -v datamodel-codegen >/dev/null 2>&1; then
    echo "ERROR: datamodel-codegen not found — install it first:" >&2
    echo "  pip install 'datamodel-code-generator[http]'" >&2
    exit 1
fi

mkdir -p "$(dirname "${OUT_FILE}")"

echo "[generate_models] generating from ${OPENAPI} -> ${OUT_FILE}"

datamodel-codegen \
    --input "${OPENAPI}" \
    --input-file-type openapi \
    --output "${OUT_FILE}" \
    --output-model-type pydantic_v2.BaseModel \
    --use-annotated \
    --use-standard-collections \
    --use-union-operator \
    --enum-field-as-literal one \
    --field-constraints \
    --strict-nullable \
    --target-python-version 3.12

echo "[generate_models] done — ${OUT_FILE} regenerated."
echo "[generate_models] sanity-check: import succeeds?"
python3 -c "import importlib.util, sys; spec = importlib.util.spec_from_file_location('_g', '${OUT_FILE}'); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); print('  symbols:', len([s for s in dir(m) if not s.startswith('_')]))"
