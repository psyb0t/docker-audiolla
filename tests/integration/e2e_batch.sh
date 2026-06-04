#!/bin/bash
# Batch operations — POST /v1/batch.
# Operates on staged files via file_path.
#
#     bash tests/integration/e2e_batch.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# Stage input fixture once for all tests.
setup_staged_input() {
    local body
    body=$(curl -s --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_path=batch_e2e/input.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    if ! echo "$body" | jq -e '.path == "batch_e2e/input.wav"' >/dev/null 2>&1; then
        echo "  FAIL: could not stage input; body: $body"; return 1
    fi
}

# ── single trim op ───────────────────────────────────────────────────────────

test_batch_single_trim() {
    setup_staged_input || return 1
    local body
    body=$(curl -s --max-time 60 -X POST \
        -H "Content-Type: application/json" \
        -d '[{"op":"trim","file_path":"batch_e2e/input.wav","output_path":"batch_e2e/trim.wav","start_sec":0,"end_sec":2}]' \
        "${AUDIOLLA_BASE_URL}/v1/batch")
    if ! echo "$body" | jq -e '.results | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: results not an array; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.results[0].status == "ok"' >/dev/null 2>&1; then
        echo "  FAIL: op failed; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.results[0].path == "batch_e2e/trim.wav"' >/dev/null 2>&1; then
        echo "  FAIL: path missing; body: $body"; return 1
    fi
    echo "OK: batch_single_trim"
}

# ── multiple ops in sequence ──────────────────────────────────────────────────

test_batch_multi_ops() {
    setup_staged_input || return 1
    local body
    body=$(curl -s --max-time 90 -X POST \
        -H "Content-Type: application/json" \
        -d '[
          {"op":"trim","file_path":"batch_e2e/input.wav","output_path":"batch_e2e/trimmed.wav","start_sec":0,"end_sec":3},
          {"op":"convert","file_path":"batch_e2e/input.wav","output_path":"batch_e2e/converted.mp3","output_format":"mp3"},
          {"op":"reverse","file_path":"batch_e2e/input.wav","output_path":"batch_e2e/reversed.wav"}
        ]' \
        "${AUDIOLLA_BASE_URL}/v1/batch")
    if ! echo "$body" | jq -e '.results | length == 3' >/dev/null 2>&1; then
        echo "  FAIL: expected 3 results; body: $body"; return 1
    fi
    # All three should succeed.
    local bad
    bad=$(echo "$body" | jq -r '[.results[] | select(.status != "ok")] | length')
    if [ "${bad:-0}" -gt 0 ]; then
        echo "  FAIL: $bad ops failed; body: $body"; return 1
    fi
    echo "OK: batch_multi_ops (3/3 ok)"
}

# ── unsupported op returns error entry, not 400 ──────────────────────────────

test_batch_unsupported_op_error_in_results() {
    setup_staged_input || return 1
    local body code
    tmpfile=$(mktemp)
    code=$(curl -s -o "$tmpfile" -w "%{http_code}" --max-time 30 -X POST \
        -H "Content-Type: application/json" \
        -d '[{"op":"nonexistent_op","file_path":"batch_e2e/input.wav"}]' \
        "${AUDIOLLA_BASE_URL}/v1/batch")
    body=$(cat "$tmpfile"); rm -f "$tmpfile"
    assert_eq "$code" "200" "unsupported op -> 200 with error entry" || return 1
    if ! echo "$body" | jq -e '.results[0].error != null' >/dev/null 2>&1; then
        echo "  FAIL: expected error entry; body: $body"; return 1
    fi
    echo "OK: batch_unsupported_op_error_in_results"
}

# ── non-JSON body → 400 ───────────────────────────────────────────────────────

test_batch_invalid_json_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -H "Content-Type: application/json" \
        -d 'not json' \
        "${AUDIOLLA_BASE_URL}/v1/batch")
    assert_eq "$code" "400" "invalid JSON body -> 400" || return 1
    echo "OK: batch_invalid_json_400"
}

# ── array body not array → 400 ───────────────────────────────────────────────

test_batch_non_array_body_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -H "Content-Type: application/json" \
        -d '{"op":"trim"}' \
        "${AUDIOLLA_BASE_URL}/v1/batch")
    assert_eq "$code" "400" "non-array body -> 400" || return 1
    echo "OK: batch_non_array_body_400"
}

# ── nonexistent file_path returns error entry ─────────────────────────────────

test_batch_nonexistent_file_path() {
    local body
    body=$(curl -s --max-time 30 -X POST \
        -H "Content-Type: application/json" \
        -d '[{"op":"trim","file_path":"batch_e2e/nonexistent.wav","start_sec":0,"end_sec":1}]' \
        "${AUDIOLLA_BASE_URL}/v1/batch")
    if ! echo "$body" | jq -e '.results[0].error != null' >/dev/null 2>&1; then
        echo "  FAIL: expected error for nonexistent path; body: $body"; return 1
    fi
    echo "OK: batch_nonexistent_file_path"
}

harness_run_tests \
    test_batch_single_trim \
    test_batch_multi_ops \
    test_batch_unsupported_op_error_in_results \
    test_batch_invalid_json_400 \
    test_batch_non_array_body_400 \
    test_batch_nonexistent_file_path
