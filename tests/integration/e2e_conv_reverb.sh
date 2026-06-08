#!/bin/bash
# Convolution reverb — /v1/audio/conv-reverb.
#
#     bash tests/integration/e2e_conv_reverb.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"
FIXTURE_DIR="${_DIR}/.fixtures"
IR_FIXTURE="${FIXTURE_DIR}/ir.wav"

harness_start "librosa-analyze"  # any engine keeps the harness happy

# Build a short decaying-noise IR fixture if missing.
build_ir_fixture() {
    if [ -f "$IR_FIXTURE" ] && [ -s "$IR_FIXTURE" ]; then
        return 0
    fi
    docker run --rm \
        --entrypoint ffmpeg \
        -v "${FIXTURE_DIR}:${FIXTURE_DIR}" \
        "$HARNESS_IMAGE" \
        -y -hide_banner -nostats \
        -f lavfi -i "anoisesrc=d=1:c=white:r=44100,volume=volume=-20dB" \
        -af "afade=t=out:st=0:d=1" \
        "$IR_FIXTURE" >/dev/null 2>&1
    [ -f "$IR_FIXTURE" ] && [ -s "$IR_FIXTURE" ] || {
        echo "  FAIL: could not build IR fixture"; return 1
    }
}

# ── basic conv-reverb returns WAV ─────────────────────────────────────────────

test_conv_reverb_returns_wav() {
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${IR_FIXTURE}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${IR_FIXTURE}")" >/dev/null || true
    build_ir_fixture || return 1
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
        -d "{\"file_path\":\"$_stage\",\"ir_file_path\":\"secondary/$(basename "${IR_FIXTURE}")\",\"wet_mix\":0.3,\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/conv-reverb")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "conv-reverb -> 200" || { rm -f "$tmpf"; return 1; }
    if [ "$(stat -c%s "$tmpf")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"; rm -f "$tmpf"; return 1
    fi
    local sz
    sz=$(stat -c%s "$tmpf")
    if [ "$sz" -lt 100000 ]; then
        echo "  FAIL: output too small ($sz bytes)"; rm -f "$tmpf"; return 1
    fi
    rm -f "$tmpf"
    echo "OK: conv_reverb_returns_wav (${sz}B)"
}

# ── wet_mix=0.0 → dry-only → output ~= input ─────────────────────────────────

test_conv_reverb_dry_only() {
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${IR_FIXTURE}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${IR_FIXTURE}")" >/dev/null || true
    build_ir_fixture || return 1
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
        -d "{\"file_path\":\"$_stage\",\"ir_file_path\":\"secondary/$(basename "${IR_FIXTURE}")\",\"wet_mix\":0.0,\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/conv-reverb")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "dry-only -> 200" || { rm -f "$tmpf"; return 1; }
    in_sz=$(stat -c%s "$FIXTURE")
    out_sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    # PCM output size should be very close to input.
    local diff lower upper
    diff=$((out_sz - in_sz))
    lower=$(( - in_sz / 10 ))
    upper=$(( in_sz / 10 ))
    if [ "$diff" -lt "$lower" ] || [ "$diff" -gt "$upper" ]; then
        echo "  FAIL: dry output ($out_sz) too far from input ($in_sz)"; return 1
    fi
    echo "OK: conv_reverb_dry_only (in=$in_sz out=$out_sz)"
}

# ── invalid wet_mix > 1 → 400 ────────────────────────────────────────────────

test_conv_reverb_invalid_wet_mix_400() {
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${IR_FIXTURE}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${IR_FIXTURE}")" >/dev/null || true
    build_ir_fixture || return 1
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"ir_file_path\":\"secondary/$(basename "${IR_FIXTURE}")\",\"wet_mix\":1.5,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/conv-reverb")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] && echo "  OK: $wet_mix=1.5 -> 422 (code=$code)" || { echo "  FAIL: $wet_mix=1.5 -> 422 expected 400 or 422, got $code"; return 1; } || return 1
    echo "OK: conv_reverb_invalid_wet_mix_400"
}

# ── output_path stages result ────────────────────────────────────────────────

test_conv_reverb_output_path() {
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${IR_FIXTURE}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${IR_FIXTURE}")" >/dev/null || true
    build_ir_fixture || return 1
    local body code fetched
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"ir_file_path\":\"secondary/$(basename "${IR_FIXTURE}")\",\"wet_mix\":0.4,\"output_path\":\"conv_reverb_test/reverbed.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/conv-reverb")
    if ! echo "$body" | jq -e '.path == "conv_reverb_test/reverbed.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/conv_reverb_test/reverbed.wav")
    assert_eq "$code" "200" "GET staged reverb file -> 200" || { rm -f "$fetched"; return 1; }
    if ! head -c 4 "$fetched" | grep -q "RIFF"; then
        echo "  FAIL: staged file not WAV"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: conv_reverb_output_path"
}

harness_run_tests \
    test_conv_reverb_returns_wav \
    test_conv_reverb_dry_only \
    test_conv_reverb_invalid_wet_mix_400 \
    test_conv_reverb_output_path
