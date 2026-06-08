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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "noise-reduce -> 200" || { rm -f "$tmpout"; return 1; }
    if [ "$(stat -c%s "$tmpout")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: noise_reduce_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── stationary=true (constant hum/hiss) mode also works ────────────────────

test_noise_reduce_stationary_mode() {
    local tmpout code
    tmpout=$(mktemp)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"stationary\":true,\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "noise-reduce stationary -> 200" || { rm -f "$tmpout"; return 1; }
    if [ "$(stat -c%s "$tmpout")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: noise_reduce_stationary_mode ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── prop_decrease=0.5 partial reduction still returns audio ─────────────────

test_noise_reduce_partial_decrease() {
    local tmpout code
    tmpout=$(mktemp)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"prop_decrease\":0.5,\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "noise-reduce prop_decrease=0.5 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ "$(stat -c%s "$tmpout")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: noise_reduce_partial_decrease ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── invalid prop_decrease > 1 → 400 ─────────────────────────────────────────

test_noise_reduce_invalid_prop_decrease_400() {
    local code body tmpf
    tmpf=$(mktemp)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"prop_decrease\":1.5,\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    body=$(cat "$tmpf" 2>/dev/null); rm -f "$tmpf"
    [[ "$code" = "400" || "$code" = "422" ]] || { echo "  FAIL: prop_decrease=1.5 -> got $code"; return 1; }
    if ! echo "$body" | grep -qi "prop_decrease"; then
        echo "  FAIL: detail missing prop_decrease; body: $body"; return 1
    fi
    echo "OK: noise_reduce_invalid_prop_decrease_400 (code=$code)"
}

# ── missing file → 400 ──────────────────────────────────────────────────────

test_noise_reduce_missing_file_404() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"file_path\":\"nonexistent/phantom.wav\"}" -o "/dev/null" -w "%{http_code}" --max-time 30 "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    [[ "$code" = "400" || "$code" = "404" || "$code" = "422" ]] || { echo "  FAIL: missing file -> got $code"; return 1; }
    echo "OK: noise_reduce_missing_file_404 (code=$code)"
}

# ── output_format=mp3 returns MP3 (check Content-Type header) ───────────────

test_noise_reduce_output_format_mp3() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.mp3"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce")
    if ! echo "$body" | jq -e '.output_format == "mp3"' >/dev/null 2>&1; then
        echo "  FAIL: expected output_format=mp3 in response; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.size > 1000' >/dev/null 2>&1; then
        echo "  FAIL: response size too small; body: $body"; return 1
    fi
    echo "OK: noise_reduce_output_format_mp3 ($(echo "$body" | jq -r '.size') bytes)"
}

# ── output is not silent — reduced audio has non-zero size ──────────────────

test_noise_reduce_output_not_empty() {
    local tmpout size
    tmpout=$(mktemp)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/noise-reduce/noise-reduce" >/dev/null
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
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
