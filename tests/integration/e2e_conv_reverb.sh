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
    build_ir_fixture || return 1
    local tmpf code
    tmpf=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "ir_file=@${IR_FIXTURE}" \
        -F "wet_mix=0.3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/conv-reverb")
    assert_eq "$code" "200" "conv-reverb -> 200" || { rm -f "$tmpf"; return 1; }
    if ! head -c 4 "$tmpf" | grep -q "RIFF"; then
        echo "  FAIL: output is not WAV"; rm -f "$tmpf"; return 1
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
    build_ir_fixture || return 1
    local tmpf code in_sz out_sz
    tmpf=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "ir_file=@${IR_FIXTURE}" \
        -F "wet_mix=0.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/conv-reverb")
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
    build_ir_fixture || return 1
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "ir_file=@${IR_FIXTURE}" \
        -F "wet_mix=1.5" \
        "${AUDIOLLA_BASE_URL}/v1/audio/conv-reverb")
    assert_eq "$code" "400" "wet_mix=1.5 -> 400" || return 1
    echo "OK: conv_reverb_invalid_wet_mix_400"
}

# ── output_path stages result ────────────────────────────────────────────────

test_conv_reverb_output_path() {
    build_ir_fixture || return 1
    local body code fetched
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "ir_file=@${IR_FIXTURE}" \
        -F "wet_mix=0.4" \
        -F "output_path=conv_reverb_test/reverbed.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/conv-reverb")
    if ! echo "$body" | jq -e '.path == "conv_reverb_test/reverbed.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/conv_reverb_test/reverbed.wav")
    assert_eq "$code" "200" "GET staged reverb file -> 200" || { rm -f "$fetched"; return 1; }
    head -c 4 "$fetched" | grep -q "RIFF" || {
        echo "  FAIL: staged file not WAV"; rm -f "$fetched"; return 1
    }
    rm -f "$fetched"
    echo "OK: conv_reverb_output_path"
}

harness_run_tests \
    test_conv_reverb_returns_wav \
    test_conv_reverb_dry_only \
    test_conv_reverb_invalid_wet_mix_400 \
    test_conv_reverb_output_path
