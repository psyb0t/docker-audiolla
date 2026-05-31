#!/bin/bash
# Endpoint smoke tests — no actual audio processing, no model loading.
# Self-contained: spawns its own container via harness.sh.
#
#     bash tests/integration/test_endpoints.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

# Use only CPU-viable engines so the test runs without a GPU.
ENDPOINTS_ENGINES="matchering,librosa-analyze,sox-transform"

harness_start "$ENDPOINTS_ENGINES"

# ── /healthz reachable, returns the configured engine slugs ──────────────────

test_healthz() {
    local out slug
    out=$(audiolla_get "/healthz") || { echo "  FAIL: /healthz unreachable"; return 1; }
    assert_contains "$out" "\"ok\":true" "/healthz ok=true" || return 1
    for slug in ${HARNESS_ENABLED_ENGINES//,/ }; do
        assert_contains "$out" "$slug" "/healthz lists $slug" || return 1
    done
    echo "OK: healthz"
}

# ── /v1/engines returns our custom list shape ────────────────────────────────

test_engines_list() {
    local out slug
    out=$(audiolla_get "/v1/engines") || { echo "  FAIL: /v1/engines unreachable"; return 1; }
    assert_contains "$out" "\"object\":\"list\"" "/v1/engines list shape" || return 1
    for slug in ${HARNESS_ENABLED_ENGINES//,/ }; do
        assert_contains "$out" "\"$slug\"" "/v1/engines has $slug" || return 1
    done
    echo "OK: engines_list"
}

# ── /api/ps responds with expected shape ─────────────────────────────────────

test_api_ps() {
    local out
    out=$(audiolla_get "/api/ps") || { echo "  FAIL: /api/ps unreachable"; return 1; }
    assert_contains "$out" "engines" "/api/ps has engines field" || return 1
    echo "OK: api_ps"
}

# ── POST /unload always 200 ──────────────────────────────────────────────────

test_unload_all() {
    local code
    code=$(audiolla_method_status POST "/unload")
    assert_eq "$code" "200" "/unload -> 200" || return 1
    echo "OK: unload_all"
}

# ── DELETE /api/ps/{unknown} returns 404 ─────────────────────────────────────

test_delete_unknown_engine() {
    local code
    code=$(audiolla_method_status DELETE "/api/ps/this-engine-does-not-exist")
    assert_eq "$code" "404" "DELETE unknown engine -> 404" || return 1
    echo "OK: delete_unknown_engine"
}

# ── POST /v1/audio/separate without file → 422 ───────────────────────────────

test_separate_missing_file_422() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "engine=htdemucs" \
        "${AUDIOLLA_BASE_URL}/v1/audio/separate")
    assert_eq "$code" "422" "separate missing file -> 422" || return 1
    echo "OK: separate_missing_file_422"
}

# ── POST /v1/audio/master with unknown mode → 400 ────────────────────────────

test_master_bad_mode_400() {
    local code tmp
    tmp=$(mktemp)
    dd if=/dev/urandom bs=100 count=1 > "$tmp" 2>/dev/null
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${tmp}" \
        -F "mode=bogus" \
        "${AUDIOLLA_BASE_URL}/v1/audio/master")
    rm -f "$tmp"
    assert_eq "$code" "400" "master bad mode -> 400" || return 1
    echo "OK: master_bad_mode_400"
}

harness_run_tests \
    test_healthz \
    test_engines_list \
    test_api_ps \
    test_unload_all \
    test_delete_unknown_engine \
    test_separate_missing_file_422 \
    test_master_bad_mode_400
