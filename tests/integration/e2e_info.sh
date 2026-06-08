#!/bin/bash
# Audio metadata probe — /v1/audio/info end-to-end.
#
#     bash tests/integration/e2e_info.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── returns JSON with required fields ────────────────────────────────────────

test_info_returns_required_fields() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info")
    for field in duration_sec sample_rate channels codec format size_bytes; do
        if ! echo "$body" | jq -e "has(\"${field}\")" >/dev/null 2>&1; then
            echo "  FAIL: missing field ${field}; body: $(echo "$body" | head -c 300)"
            return 1
        fi
    done
    echo "OK: info_returns_required_fields"
}

# ── duration_sec is a positive number ────────────────────────────────────────

test_info_duration_is_positive() {
    local dur
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    dur=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')
    if ! python3 -c "assert float('${dur}') > 0, 'duration <= 0'" 2>/dev/null; then
        echo "  FAIL: duration_sec not positive: ${dur}"; return 1
    fi
    echo "OK: info_duration_is_positive (${dur}s)"
}

# ── sample_rate matches fixture (44100 Hz) ───────────────────────────────────

test_info_sample_rate_44100() {
    local sr
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    sr=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.sample_rate')
    assert_eq "$sr" "44100" "sample_rate == 44100" || return 1
    echo "OK: info_sample_rate_44100"
}

# ── channels matches fixture (2 = stereo) ────────────────────────────────────

test_info_channels_stereo() {
    local ch
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    ch=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.channels')
    assert_eq "$ch" "2" "channels == 2 (stereo)" || return 1
    echo "OK: info_channels_stereo"
}

# ── size_bytes matches actual file size ──────────────────────────────────────

test_info_size_bytes_matches_file() {
    local actual_size reported_size
    actual_size=$(stat -c%s "$FIXTURE")
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    reported_size=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.size_bytes')
    assert_eq "$reported_size" "$actual_size" "size_bytes matches file" || return 1
    echo "OK: info_size_bytes_matches_file (${actual_size} bytes)"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_info_missing_file_400() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"file_path\":\"no/such.wav\"}" -o "/dev/null" -w "%{http_code}" --max-time 30 "${AUDIOLLA_BASE_URL}/v1/audio/info")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: info_missing_file_400"
}

# ── no file at all → 422 (required field) ────────────────────────────────────

test_info_no_input_422() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        "${AUDIOLLA_BASE_URL}/v1/audio/info")
    assert_eq "$code" "422" "no input -> 422" || return 1
    echo "OK: info_no_input_422"
}

harness_run_tests \
    test_info_returns_required_fields \
    test_info_duration_is_positive \
    test_info_sample_rate_44100 \
    test_info_channels_stereo \
    test_info_size_bytes_matches_file \
    test_info_missing_file_400 \
    test_info_no_input_422
