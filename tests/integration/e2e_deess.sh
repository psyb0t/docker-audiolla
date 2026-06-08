#!/bin/bash
# De-esser — /v1/audio/deess.
#
#     bash tests/integration/e2e_deess.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── default params return same-length WAV ────────────────────────────────────

test_deess_default_returns_wav() {
    local tmpf code in_sz out_sz
    tmpf=$(mktemp --suffix=.wav)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/deess")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "deess default -> 200" || { rm -f "$tmpf"; return 1; }
    if [ "$(stat -c%s "$tmpf")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"; rm -f "$tmpf"; return 1
    fi
    in_sz=$(stat -c%s "$FIXTURE")
    out_sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    local diff lower upper
    diff=$((out_sz - in_sz))
    lower=$(( -in_sz / 20 ))
    upper=$(( in_sz / 20 ))
    if [ "$diff" -lt "$lower" ] || [ "$diff" -gt "$upper" ]; then
        echo "  FAIL: output size ($out_sz) too far from input ($in_sz)"; return 1
    fi
    echo "OK: deess_default_returns_wav (in=$in_sz out=$out_sz)"
}

# ── output_path stages WAV + returns JSON with params ────────────────────────

test_deess_output_path() {
    local body code fetched
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"threshold_db\":-15,\"frequency_hz\":7000,\"output_path\":\"deess_test/out.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/deess")
    if ! echo "$body" | jq -e '.path == "deess_test/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: path missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.threshold_db == -15' >/dev/null 2>&1; then
        echo "  FAIL: threshold_db missing from response; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/deess_test/out.wav")
    assert_eq "$code" "200" "GET staged deess -> 200" || { rm -f "$fetched"; return 1; }
    if ! head -c 4 "$fetched" | grep -q "RIFF"; then
        echo "  FAIL: staged file not WAV"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: deess_output_path"
}

# ── mp3 output format ────────────────────────────────────────────────────────

test_deess_output_format_mp3() {
    local code tmpf
    tmpf=$(mktemp --suffix=.mp3)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/deess")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "deess mp3 -> 200" || { rm -f "$tmpf"; return 1; }
    if [ ! -s "$tmpf" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpf"; return 1
    fi
    rm -f "$tmpf"
    echo "OK: deess_output_format_mp3"
}

# ── ratio out of range → 400 ─────────────────────────────────────────────────

test_deess_invalid_ratio_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"ratio\":100,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/deess")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] && echo "  OK: $ratio=100 -> 422 (code=$code)" || { echo "  FAIL: $ratio=100 -> 422 expected 400 or 422, got $code"; return 1; } || return 1
    echo "OK: deess_invalid_ratio_400"
}

# ── frequency_hz out of range → 400 ──────────────────────────────────────────

test_deess_invalid_frequency_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"frequency_hz\":100,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/deess")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] || { echo "  FAIL: frequency_hz=100 expected 400/422, got $code"; return 1; }
    echo "OK: deess_invalid_frequency_400 (code=$code)"
}

harness_run_tests \
    test_deess_default_returns_wav \
    test_deess_output_path \
    test_deess_output_format_mp3 \
    test_deess_invalid_ratio_400 \
    test_deess_invalid_frequency_400
