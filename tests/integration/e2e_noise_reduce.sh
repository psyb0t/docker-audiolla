#!/bin/bash
# Spectral noise reduction — /v1/audio/noise-reduce/{engine} end-to-end.
#
#     bash tests/integration/e2e_noise_reduce.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "noise-reduce"

# ── default (non-stationary) mode returns valid WAV ─────────────────────────

test_noise_reduce_returns_wav() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    assert_eq "$code" "200" "noise-reduce -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: noise_reduce_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── stationary=true (constant hum/hiss) mode also works ────────────────────

test_noise_reduce_stationary_mode() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "stationary=true" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    assert_eq "$code" "200" "noise-reduce stationary -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV (stationary mode)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: noise_reduce_stationary_mode ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── prop_decrease=0.5 partial reduction still returns audio ─────────────────

test_noise_reduce_partial_decrease() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "prop_decrease=0.5" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    assert_eq "$code" "200" "noise-reduce prop_decrease=0.5 -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV (prop_decrease=0.5)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: noise_reduce_partial_decrease ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── invalid prop_decrease > 1 → 400 ─────────────────────────────────────────

test_noise_reduce_invalid_prop_decrease_400() {
    local code body tmpf
    tmpf=$(mktemp)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "prop_decrease=1.5" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    body=$(cat "$tmpf" 2>/dev/null); rm -f "$tmpf"
    assert_eq "$code" "400" "prop_decrease=1.5 -> 400" || return 1
    if ! echo "$body" | grep -qi "prop_decrease"; then
        echo "  FAIL: detail missing prop_decrease; body: $body"; return 1
    fi
    echo "OK: noise_reduce_invalid_prop_decrease_400"
}

# ── missing file → 400 ──────────────────────────────────────────────────────

test_noise_reduce_missing_file_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=nonexistent/phantom.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    assert_eq "$code" "404" "missing file_path -> 404" || return 1
    echo "OK: noise_reduce_missing_file_404"
}

# ── output_format=mp3 returns MP3 (check Content-Type header) ───────────────

test_noise_reduce_output_format_mp3() {
    local ct
    ct=$(curl -s -o /dev/null -w "%{content_type}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    if [[ "$ct" != *"audio/mpeg"* && "$ct" != *"audio/mp3"* ]]; then
        echo "  FAIL: expected audio/mpeg content-type, got: $ct"; return 1
    fi
    echo "OK: noise_reduce_output_format_mp3 (content-type: $ct)"
}

# ── output is not silent — reduced audio has non-zero size ──────────────────

test_noise_reduce_output_not_empty() {
    local tmpout size
    tmpout=$(mktemp)
    curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce" > "$tmpout"
    size=$(stat -c%s "$tmpout")
    rm -f "$tmpout"
    if [ "$size" -lt 1000 ]; then
        echo "  FAIL: output suspiciously small ($size bytes)"; return 1
    fi
    echo "OK: noise_reduce_output_not_empty ($size bytes)"
}

harness_run_tests \
    test_noise_reduce_returns_wav \
    test_noise_reduce_stationary_mode \
    test_noise_reduce_partial_decrease \
    test_noise_reduce_invalid_prop_decrease_400 \
    test_noise_reduce_missing_file_404 \
    test_noise_reduce_output_format_mp3 \
    test_noise_reduce_output_not_empty
