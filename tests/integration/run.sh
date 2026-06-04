#!/bin/bash
# audiolla integration test dispatcher.
#
# Each test_*.sh / e2e_*.sh in this directory is self-contained: it spawns
# its own container via harness.sh, runs its checks, tears the container
# down on exit. Per-file invocation also works:
#
#     bash tests/integration/test_endpoints.sh
#     bash tests/integration/e2e_separation.sh
#
# Env knobs:
#   AUDIOLLA_SKIP_BUILD=1  skip `make build` — use whatever's tagged
#   HARNESS_IMAGE          override the docker image tag
#   HARNESS_CACHE_DIR      override the on-host /data cache dir

set -eo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/../.."

command -v docker >/dev/null 2>&1 || { echo "FATAL: docker not on PATH" >&2; exit 2; }
command -v curl   >/dev/null 2>&1 || { echo "FATAL: curl not on PATH"   >&2; exit 2; }
command -v jq     >/dev/null 2>&1 || { echo "FATAL: jq not on PATH"     >&2; exit 2; }

if [ "${AUDIOLLA_SKIP_BUILD:-0}" != "1" ]; then
    echo "[run] building CPU image..."
    make build 2>&1 | tail -3
fi
export HARNESS_SKIP_BUILD=1

_DIR="$(dirname "${BASH_SOURCE[0]}")"

shopt -s nullglob
declare -a TEST_FILES
for f in "$_DIR"/test_*.sh "$_DIR"/e2e_*.sh; do
    TEST_FILES+=("$(basename "$f")")
done
shopt -u nullglob

if [ "$#" -gt 0 ]; then
    SELECTED=("$@")
else
    SELECTED=("${TEST_FILES[@]}")
fi

if [ "${#SELECTED[@]}" -eq 0 ]; then
    echo "[run] no test files found in $_DIR" >&2
    exit 1
fi

PASS=0
FAIL=0
FAILED=()

for tf in "${SELECTED[@]}"; do
    full="${_DIR}/${tf}"
    if [ ! -f "$full" ]; then
        echo ""
        echo "[run] SKIP: $tf — file not found"
        continue
    fi
    echo ""
    echo "============================================================="
    echo "  RUN  $tf"
    echo "============================================================="
    if bash "$full"; then
        PASS=$((PASS + 1))
    else
        FAIL=$((FAIL + 1))
        FAILED+=("$tf")
    fi
done

echo ""
echo "═══════════════════════════════════════════════════════════"
echo "  integration suite: pass=$PASS fail=$FAIL total=$((PASS + FAIL))"
if [ "$FAIL" -ne 0 ]; then
    echo "  failed files:"
    for tf in "${FAILED[@]}"; do
        echo "    - $tf"
    done
fi
echo "═══════════════════════════════════════════════════════════"

[ "$FAIL" -eq 0 ]
