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
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_format=wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    assert_eq "$code" "200" "convert wav -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: convert_wav_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── WAV → MP3 ─────────────────────────────────────────────────────────────────

test_convert_wav_to_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
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
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_format=flac" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    assert_eq "$code" "200" "convert flac -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty flac response"; rm -f "$tmpout"; return 1
    fi
    echo "OK: convert_wav_to_flac ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── sample_rate conversion ────────────────────────────────────────────────────

test_convert_sample_rate() {
    local tmpout body sr
    tmpout=$(mktemp --suffix=.wav)
    curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_format=wav" \
        -F "sample_rate=22050" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert" > "$tmpout"
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${tmpout}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info")
    rm -f "$tmpout"
    sr=$(echo "$body" | jq -r '.sample_rate')
    assert_eq "$sr" "22050" "sample_rate=22050" || return 1
    echo "OK: convert_sample_rate (sr=${sr})"
}

# ── channels=1 → mono ─────────────────────────────────────────────────────────

test_convert_to_mono() {
    local tmpout body ch
    tmpout=$(mktemp --suffix=.wav)
    curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_format=wav" \
        -F "channels=1" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert" > "$tmpout"
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${tmpout}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info")
    rm -f "$tmpout"
    ch=$(echo "$body" | jq -r '.channels')
    assert_eq "$ch" "1" "channels=1 (mono)" || return 1
    echo "OK: convert_to_mono"
}

# ── channels=3 → 400 ─────────────────────────────────────────────────────────

test_convert_invalid_channels_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "channels=3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    assert_eq "$code" "400" "channels=3 -> 400" || return 1
    echo "OK: convert_invalid_channels_400"
}

# ── sample_rate=0 → 400 ───────────────────────────────────────────────────────

test_convert_invalid_sample_rate_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "sample_rate=0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    assert_eq "$code" "400" "sample_rate=0 -> 400" || return 1
    echo "OK: convert_invalid_sample_rate_400"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_convert_missing_file_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: convert_missing_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_convert_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_format=mp3" \
        -F "output_path=convert/out.mp3" \
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
