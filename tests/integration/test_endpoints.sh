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

FIXTURE="${_DIR}/.fixtures/audio.wav"

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

# ── POST /v1/audio/transform with no input mode → 400 ───────────────────────
# Before the input_resolver refactor this was 422 (FastAPI's generic
# "field required"). Now it's a 400 with a message naming all three input
# modes, which is more useful to callers.
# Using /v1/audio/transform because this harness has sox-transform enabled
# (the separation engines need their own harness).

test_transform_missing_input_400() {
    local code body
    body=$(curl -s -o /tmp/audiolla-endpoint-body.$$ -w "%{http_code}" \
        --max-time 30 -X POST \
        -F "operations=[]" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    code="$body"
    body=$(cat /tmp/audiolla-endpoint-body.$$ 2>/dev/null)
    rm -f /tmp/audiolla-endpoint-body.$$
    assert_eq "$code" "400" "transform no input -> 400" || return 1
    if ! echo "$body" | grep -q "file_path"; then
        echo "  FAIL: detail does not mention file_path; got: $body"
        return 1
    fi
    if ! echo "$body" | grep -q "file_url"; then
        echo "  FAIL: detail does not mention file_url; got: $body"
        return 1
    fi
    echo "OK: transform_missing_input_400"
}

# ── Two input modes simultaneously → 400 ─────────────────────────────────────

test_transform_two_inputs_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "file_path=does-not-matter" \
        -F "operations=[]" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    assert_eq "$code" "400" "transform file + file_path -> 400" || return 1
    echo "OK: transform_two_inputs_400"
}

# ── file_url with default disabled policy → 400 ──────────────────────────────

test_file_url_disabled_by_default_400() {
    local code body
    body=$(curl -s -o /tmp/audiolla-endpoint-body.$$ -w "%{http_code}" \
        --max-time 30 -X POST \
        -F "file_url=https://example.com/track.wav" \
        -F "operations=[]" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    code="$body"
    body=$(cat /tmp/audiolla-endpoint-body.$$ 2>/dev/null)
    rm -f /tmp/audiolla-endpoint-body.$$
    assert_eq "$code" "400" "file_url disabled -> 400" || return 1
    if ! echo "$body" | grep -qi "disabled"; then
        echo "  FAIL: detail does not mention disabled; got: $body"
        return 1
    fi
    echo "OK: file_url_disabled_by_default_400"
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
    test_transform_missing_input_400 \
    test_transform_two_inputs_400 \
    test_file_url_disabled_by_default_400 \
    test_master_bad_mode_400
