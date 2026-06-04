#!/bin/bash
# Mid/Side encode and decode — /v1/audio/mid-side.
#
#     bash tests/integration/e2e_mid_side.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"  # any engine keeps the harness happy

# ── encode returns stereo WAV ─────────────────────────────────────────────────

test_mid_side_encode_returns_wav() {
    local tmpf code
    tmpf=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "mode=encode" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    assert_eq "$code" "200" "encode -> 200" || { rm -f "$tmpf"; return 1; }
    if ! head -c 4 "$tmpf" | grep -q "RIFF"; then
        echo "  FAIL: output is not WAV"
        rm -f "$tmpf"; return 1
    fi
    local sz
    sz=$(stat -c%s "$tmpf")
    if [ "$sz" -lt 100000 ]; then
        echo "  FAIL: output too small ($sz bytes)"; rm -f "$tmpf"; return 1
    fi
    rm -f "$tmpf"
    echo "OK: mid_side_encode_returns_wav (${sz}B)"
}

# ── decode returns stereo WAV ─────────────────────────────────────────────────

test_mid_side_decode_returns_wav() {
    local tmpf code
    tmpf=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "mode=decode" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    assert_eq "$code" "200" "decode -> 200" || { rm -f "$tmpf"; return 1; }
    if ! head -c 4 "$tmpf" | grep -q "RIFF"; then
        echo "  FAIL: output is not WAV"
        rm -f "$tmpf"; return 1
    fi
    rm -f "$tmpf"
    echo "OK: mid_side_decode_returns_wav"
}

# ── encode → decode round-trip: same size as original ────────────────────────

test_mid_side_roundtrip() {
    local enc_f dec_f code orig_sz dec_sz
    enc_f=$(mktemp --suffix=.wav)
    dec_f=$(mktemp --suffix=.wav)
    # Encode.
    code=$(curl -s -o "$enc_f" -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" -F "mode=encode" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    assert_eq "$code" "200" "encode -> 200" || { rm -f "$enc_f" "$dec_f"; return 1; }
    # Decode the encoded file.
    code=$(curl -s -o "$dec_f" -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${enc_f}" -F "mode=decode" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    assert_eq "$code" "200" "decode -> 200" || { rm -f "$enc_f" "$dec_f"; return 1; }
    orig_sz=$(stat -c%s "$FIXTURE")
    dec_sz=$(stat -c%s "$dec_f")
    rm -f "$enc_f" "$dec_f"
    # Allow ±5% size drift (PCM headers / padding).
    local diff lower upper
    diff=$((dec_sz - orig_sz))
    lower=$(( - orig_sz / 20 ))
    upper=$(( orig_sz / 20 ))
    if [ "$diff" -lt "$lower" ] || [ "$diff" -gt "$upper" ]; then
        echo "  FAIL: decoded size ($dec_sz) too far from original ($orig_sz)"; return 1
    fi
    echo "OK: mid_side_roundtrip (orig=${orig_sz} decoded=${dec_sz})"
}

# ── output_path stages result ────────────────────────────────────────────────

test_mid_side_output_path() {
    local body code fetched
    body=$(curl -s --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "mode=encode" \
        -F "output_path=ms_test/encoded.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    if ! echo "$body" | jq -e '.path == "ms_test/encoded.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/ms_test/encoded.wav")
    assert_eq "$code" "200" "GET staged MS file -> 200" || { rm -f "$fetched"; return 1; }
    head -c 4 "$fetched" | grep -q "RIFF" || {
        echo "  FAIL: staged file not WAV"; rm -f "$fetched"; return 1
    }
    rm -f "$fetched"
    echo "OK: mid_side_output_path"
}

# ── invalid mode → 400 ───────────────────────────────────────────────────────

test_mid_side_invalid_mode_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "mode=invalid_mode" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    assert_eq "$code" "400" "invalid mode -> 400" || return 1
    echo "OK: mid_side_invalid_mode_400"
}

harness_run_tests \
    test_mid_side_encode_returns_wav \
    test_mid_side_decode_returns_wav \
    test_mid_side_roundtrip \
    test_mid_side_output_path \
    test_mid_side_invalid_mode_400
