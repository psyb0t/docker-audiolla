#!/bin/bash
# Audio convert — /v1/audio/convert end-to-end.
#
#     bash tests/integration/e2e_convert.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── WAV → WAV passthrough ─────────────────────────────────────────────────────

test_convert_wav_returns_wav() {
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
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"wav\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "convert wav -> 200" || { rm -f "$tmpout"; return 1; }
    if [ "$(stat -c%s "$tmpout")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: convert_wav_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── WAV → MP3 ─────────────────────────────────────────────────────────────────

test_convert_wav_to_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "convert mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3 response"; rm -f "$tmpout"; return 1
    fi
    echo "OK: convert_wav_to_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── WAV → FLAC ────────────────────────────────────────────────────────────────

test_convert_wav_to_flac() {
    local code tmpout
    tmpout=$(mktemp)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"flac\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "convert flac -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty flac response"; rm -f "$tmpout"; return 1
    fi
    echo "OK: convert_wav_to_flac ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── sample_rate conversion ────────────────────────────────────────────────────

test_convert_sample_rate() {
    local body sr
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/sr-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    # Convert response carries sample_rate directly.
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"wav\",\"sample_rate\":22050,\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    sr=$(echo "$body" | jq -r '.sample_rate')
    if [ "$sr" = "null" ] || [ -z "$sr" ]; then
        # Fall back to /v1/audio/info on the staged output.
        body=$(curl -s -X POST -H "Content-Type: application/json" \
            -d "{\"file_path\":\"$_out\"}" \
            "${AUDIOLLA_BASE_URL}/v1/audio/info")
        sr=$(echo "$body" | jq -r '.sample_rate')
    fi
    assert_eq "$sr" "22050" "sample_rate=22050" || return 1
    echo "OK: convert_sample_rate (sr=${sr})"
}

# ── channels=1 → mono ─────────────────────────────────────────────────────────

test_convert_to_mono() {
    local body ch
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/mono-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"wav\",\"channels\":1,\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    ch=$(echo "$body" | jq -r '.channels')
    if [ "$ch" = "null" ] || [ -z "$ch" ]; then
        body=$(curl -s -X POST -H "Content-Type: application/json" \
            -d "{\"file_path\":\"$_out\"}" \
            "${AUDIOLLA_BASE_URL}/v1/audio/info")
        ch=$(echo "$body" | jq -r '.channels')
    fi
    assert_eq "$ch" "1" "channels=1 (mono)" || return 1
    echo "OK: convert_to_mono"
}

# ── channels=3 → 400 ─────────────────────────────────────────────────────────

test_convert_invalid_channels_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"channels\":3,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "400" "channels=3 -> 400" || return 1
    echo "OK: convert_invalid_channels_400"
}

# ── sample_rate=0 → 400 ───────────────────────────────────────────────────────

test_convert_invalid_sample_rate_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"sample_rate\":0,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "400" "sample_rate=0 -> 400" || return 1
    echo "OK: convert_invalid_sample_rate_400"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_convert_missing_file_404() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"file_path\":\"no/such.wav\",\"output_path\":\"out/missing.wav\"}" -o "/dev/null" -w "%{http_code}" --max-time 30 "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: convert_missing_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_convert_output_path() {
    local body code tmpout
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"mp3\",\"output_path\":\"convert/out.mp3\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    if ! echo "$body" | jq -e '.path == "convert/out.mp3"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/convert/out.mp3")
    assert_eq "$code" "200" "GET staged convert -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: staged file empty"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: convert_output_path"
}

harness_run_tests \
    test_convert_wav_returns_wav \
    test_convert_wav_to_mp3 \
    test_convert_wav_to_flac \
    test_convert_sample_rate \
    test_convert_to_mono \
    test_convert_invalid_channels_400 \
    test_convert_invalid_sample_rate_400 \
    test_convert_missing_file_404 \
    test_convert_output_path
