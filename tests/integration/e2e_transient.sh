#!/bin/bash
# Transient shaper — /v1/audio/transient.
#
#     bash tests/integration/e2e_transient.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"  # any engine keeps the harness happy

# ── default params returns same-size WAV ─────────────────────────────────────

test_transient_default_params_returns_wav() {
    local tmpf code
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
        "${AUDIOLLA_BASE_URL}/v1/audio/transient")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "transient default -> 200" || { rm -f "$tmpf"; return 1; }
    if [ "$(stat -c%s "$tmpf")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"; rm -f "$tmpf"; return 1
    fi
    local sz
    sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    if [ "$sz" -lt 100000 ]; then
        echo "  FAIL: output too small ($sz bytes)"; return 1
    fi
    echo "OK: transient_default_params_returns_wav (${sz}B)"
}

# ── attack boost returns same-length audio ────────────────────────────────────

test_transient_attack_boost() {
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
        -d "{\"file_path\":\"$_stage\",\"attack_gain_db\":6,\"sustain_gain_db\":0,\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transient")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "attack boost -> 200" || { rm -f "$tmpf"; return 1; }
    in_sz=$(stat -c%s "$FIXTURE")
    out_sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    local diff lower upper
    diff=$((out_sz - in_sz))
    lower=$(( - in_sz / 20 ))
    upper=$(( in_sz / 20 ))
    if [ "$diff" -lt "$lower" ] || [ "$diff" -gt "$upper" ]; then
        echo "  FAIL: output size ($out_sz) too far from input ($in_sz)"; return 1
    fi
    echo "OK: transient_attack_boost (in=$in_sz out=$out_sz)"
}

# ── sustain cut + attack boost ───────────────────────────────────────────────

test_transient_sustain_cut() {
    local tmpf code
    tmpf=$(mktemp --suffix=.wav)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"attack_gain_db\":3,\"sustain_gain_db\":-6,\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transient")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "sustain cut -> 200" || { rm -f "$tmpf"; return 1; }
    [ -s "$tmpf" ] || {
        echo "  FAIL: output not WAV"; rm -f "$tmpf"; return 1
    }
    rm -f "$tmpf"
    echo "OK: transient_sustain_cut"
}

# ── output_path stages result ────────────────────────────────────────────────

test_transient_output_path() {
    local body code fetched
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"attack_gain_db\":3,\"output_path\":\"transient_test/shaped.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transient")
    if ! echo "$body" | jq -e '.path == "transient_test/shaped.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.attack_gain_db == 3' >/dev/null 2>&1; then
        echo "  FAIL: attack_gain_db missing from response; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/transient_test/shaped.wav")
    assert_eq "$code" "200" "GET staged transient -> 200" || { rm -f "$fetched"; return 1; }
    head -c 4 "$fetched" | grep -q "RIFF" || {
        echo "  FAIL: staged file not WAV"; rm -f "$fetched"; return 1
    }
    rm -f "$fetched"
    echo "OK: transient_output_path"
}

harness_run_tests \
    test_transient_default_params_returns_wav \
    test_transient_attack_boost \
    test_transient_sustain_cut \
    test_transient_output_path
