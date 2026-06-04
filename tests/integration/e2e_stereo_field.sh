#!/bin/bash
# Stereo field analysis — /v1/audio/stereo-field.
#
#     bash tests/integration/e2e_stereo_field.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── stereo file returns all expected fields ───────────────────────────────────

test_stereo_field_shape() {
    local body
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-field")
    for field in correlation width balance_db mono_compatible mid_level_db side_level_db phase_issues channels sample_rate duration; do
        if ! echo "$body" | jq -e "has(\"$field\")" >/dev/null 2>&1; then
            echo "  FAIL: field '$field' missing; body: $body"; return 1
        fi
    done
    echo "OK: stereo_field_shape"
}

# ── correlation in [-1, 1] ────────────────────────────────────────────────────

test_stereo_field_correlation_range() {
    local body corr
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-field")
    if ! echo "$body" | jq -e '.correlation >= -1 and .correlation <= 1' >/dev/null 2>&1; then
        corr=$(echo "$body" | jq -r '.correlation')
        echo "  FAIL: correlation $corr not in [-1,1]; body: $body"; return 1
    fi
    corr=$(echo "$body" | jq -r '.correlation')
    echo "OK: stereo_field_correlation_range (corr=$corr)"
}

# ── stereo sine fixture: correlation is 1.0 (L==R) ───────────────────────────
# The fixture is generated with pan=stereo|c0=c0|c1=c0, so L and R are identical.

test_stereo_field_sine_is_correlated() {
    local body corr
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-field")
    corr=$(echo "$body" | jq -r '.correlation')
    if ! echo "$body" | jq -e '.correlation > 0.99' >/dev/null 2>&1; then
        echo "  FAIL: sine (L==R) should have corr≈1.0, got $corr"; return 1
    fi
    if ! echo "$body" | jq -e '.mono_compatible == true' >/dev/null 2>&1; then
        echo "  FAIL: mono_compatible should be true for correlated signal; body: $body"; return 1
    fi
    echo "OK: stereo_field_sine_is_correlated (corr=$corr mono_compatible=true)"
}

# ── width is non-negative ─────────────────────────────────────────────────────

test_stereo_field_width_nonneg() {
    local body width
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-field")
    if ! echo "$body" | jq -e '.width >= 0' >/dev/null 2>&1; then
        width=$(echo "$body" | jq -r '.width')
        echo "  FAIL: width $width < 0; body: $body"; return 1
    fi
    width=$(echo "$body" | jq -r '.width')
    echo "OK: stereo_field_width_nonneg (width=$width)"
}

# ── file_path mode works ──────────────────────────────────────────────────────

test_stereo_field_file_path() {
    local staged_body body
    staged_body=$(curl -s --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_path=stereofield_test/in.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    if ! echo "$staged_body" | jq -e '.path == "stereofield_test/in.wav"' >/dev/null 2>&1; then
        echo "  FAIL: staging failed; body: $staged_body"; return 1
    fi
    body=$(curl -s --max-time 60 -X POST \
        -F "file_path=stereofield_test/in.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-field")
    if ! echo "$body" | jq -e 'has("correlation")' >/dev/null 2>&1; then
        echo "  FAIL: missing correlation for file_path mode; body: $body"; return 1
    fi
    echo "OK: stereo_field_file_path"
}

harness_run_tests \
    test_stereo_field_shape \
    test_stereo_field_correlation_range \
    test_stereo_field_sine_is_correlated \
    test_stereo_field_width_nonneg \
    test_stereo_field_file_path
