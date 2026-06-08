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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"encode\",\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "encode -> 200" || { rm -f "$tmpf"; return 1; }
    if [ "$(stat -c%s "$tmpf")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"decode\",\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "decode -> 200" || { rm -f "$tmpf"; return 1; }
    if [ "$(stat -c%s "$tmpf")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"encode\",\"output_path\":\"$_out\"}" \
        -o "$enc_f" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$enc_f" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "encode -> 200" || { rm -f "$enc_f" "$dec_f"; return 1; }
    # Decode the encoded file.
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${enc_f}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${enc_f}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"decode\",\"output_path\":\"$_out\"}" \
        -o "$dec_f" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$dec_f" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"encode\",\"output_path\":\"ms_test/encoded.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    if ! echo "$body" | jq -e '.path == "ms_test/encoded.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/ms_test/encoded.wav")
    assert_eq "$code" "200" "GET staged MS file -> 200" || { rm -f "$fetched"; return 1; }
    if [ "$(head -c 4 "$fetched")" != "RIFF" ]; then
        echo "  FAIL: staged file not WAV (first 4 bytes: $(head -c 4 "$fetched" | xxd -p))"
        rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: mid_side_output_path"
}

# ── invalid mode → 400 ───────────────────────────────────────────────────────

test_mid_side_invalid_mode_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"invalid_mode\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mid-side")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "422" "invalid mode -> 422" || return 1
    echo "OK: mid_side_invalid_mode_400"
}

harness_run_tests \
    test_mid_side_encode_returns_wav \
    test_mid_side_decode_returns_wav \
    test_mid_side_roundtrip \
    test_mid_side_output_path \
    test_mid_side_invalid_mode_400
