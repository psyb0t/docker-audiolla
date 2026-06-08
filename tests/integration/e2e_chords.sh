#!/bin/bash
# Chord and key detection — /v1/audio/chords.
#
#     bash tests/integration/e2e_chords.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "chord-detect"

# ── basic: returns key + chords array ────────────────────────────────────────

test_chords_returns_key_and_chords() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/chords")
    if ! echo "$body" | jq -e '.key | type == "string" and length > 0' >/dev/null 2>&1; then
        echo "  FAIL: key missing or empty; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.chords | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: chords not an array; body: $body"; return 1
    fi
    echo "OK: chords_returns_key_and_chords (key=$(echo "$body" | jq -r '.key'))"
}

# ── missing file → 4xx ───────────────────────────────────────────────────────

test_chords_rejects_missing_file() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        "${AUDIOLLA_BASE_URL}/v1/audio/chords")
    if [ "$code" -lt 400 ] || [ "$code" -ge 500 ]; then
        echo "  FAIL: expected 4xx, got $code"; return 1
    fi
    echo "OK: chords_rejects_missing_file (HTTP $code)"
}

# ── custom hop_length ────────────────────────────────────────────────────────

test_chords_custom_hop_length() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"hop_length\":1024}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/chords")
    if ! echo "$body" | jq -e '.key | type == "string"' >/dev/null 2>&1; then
        echo "  FAIL: key missing with custom hop_length; body: $body"; return 1
    fi
    echo "OK: chords_custom_hop_length"
}

# ── segment_min_duration_sec merges short segments ───────────────────────────

test_chords_segment_min_duration_sec() {
    local body_short body_long count_short count_long
    # Large min duration merges more aggressively → fewer or equal segments.
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body_short=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"segment_min_duration_sec\":0.1}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/chords")
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body_long=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"segment_min_duration_sec\":2.0}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/chords")
    if ! echo "$body_short" | jq -e '.chords | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: chords missing for segment_min_duration_sec=0.1; body: $body_short"; return 1
    fi
    if ! echo "$body_long" | jq -e '.chords | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: chords missing for segment_min_duration_sec=2.0; body: $body_long"; return 1
    fi
    count_short=$(echo "$body_short" | jq -r '.chords | length')
    count_long=$(echo "$body_long" | jq -r '.chords | length')
    if [ "$count_long" -gt "$count_short" ]; then
        echo "  FAIL: larger min_duration produced MORE segments ($count_short vs $count_long)"
        return 1
    fi
    echo "OK: chords_segment_min_duration_sec (short=$count_short long=$count_long)"
}

harness_run_tests \
    test_chords_returns_key_and_chords \
    test_chords_rejects_missing_file \
    test_chords_custom_hop_length \
    test_chords_segment_min_duration_sec
