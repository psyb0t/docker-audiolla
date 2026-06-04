#!/bin/bash
# Loudness curve (RMS envelope) — /v1/audio/loudness/curve.
#
#     bash tests/integration/e2e_loudness_curve.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── response shape ────────────────────────────────────────────────────────────

test_loudness_curve_shape() {
    local body
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness/curve")
    if ! echo "$body" | jq -e '.curve | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: curve not an array; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.duration > 0' >/dev/null 2>&1; then
        echo "  FAIL: duration missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.points > 0' >/dev/null 2>&1; then
        echo "  FAIL: points missing; body: $body"; return 1
    fi
    echo "OK: loudness_curve_shape"
}

# ── curve entries have required fields ───────────────────────────────────────

test_loudness_curve_entry_fields() {
    local body
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness/curve")
    if ! echo "$body" | jq -e '.curve[0].time_sec | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: time_sec missing in first entry; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.curve[0].rms_db | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: rms_db missing in first entry; body: $body"; return 1
    fi
    echo "OK: loudness_curve_entry_fields"
}

# ── file_path staging round-trip ─────────────────────────────────────────────

test_loudness_curve_file_path() {
    curl -s --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_path=lc_test/audio.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert" >/dev/null
    local body
    body=$(curl -s --max-time 60 -X POST \
        -F "file_path=lc_test/audio.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness/curve")
    if ! echo "$body" | jq -e '.curve | length > 0' >/dev/null 2>&1; then
        echo "  FAIL: no curve points; body: $body"; return 1
    fi
    echo "OK: loudness_curve_file_path"
}

# ── custom hop_length accepted ────────────────────────────────────────────────

test_loudness_curve_custom_hop() {
    local body
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "hop_length=1024" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness/curve")
    if ! echo "$body" | jq -e '.hop_length == 1024' >/dev/null 2>&1; then
        echo "  FAIL: hop_length not reflected in response; body: $body"; return 1
    fi
    echo "OK: loudness_curve_custom_hop"
}

harness_run_tests \
    test_loudness_curve_shape \
    test_loudness_curve_entry_fields \
    test_loudness_curve_file_path \
    test_loudness_curve_custom_hop
