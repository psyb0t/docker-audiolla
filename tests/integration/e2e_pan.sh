#!/bin/bash
# Audio pan — /v1/audio/pan end-to-end.
#
#     bash tests/integration/e2e_pan.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── center (default) → 200 WAV ────────────────────────────────────────────────

test_pan_center() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pan")
    assert_eq "$code" "200" "pan center -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: pan_center ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── hard left (-1.0) accepted ─────────────────────────────────────────────────

test_pan_hard_left() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "position=-1.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pan")
    assert_eq "$code" "200" "pan hard left -> 200" || return 1
    echo "OK: pan_hard_left"
}

# ── hard right (+1.0) accepted ────────────────────────────────────────────────

test_pan_hard_right() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "position=1.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pan")
    assert_eq "$code" "200" "pan hard right -> 200" || return 1
    echo "OK: pan_hard_right"
}

# ── output is stereo ─────────────────────────────────────────────────────────

test_pan_output_stereo() {
    local tmpout body ch
    tmpout=$(mktemp --suffix=.wav)
    curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "position=0.5" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pan" > "$tmpout"
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${tmpout}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info")
    rm -f "$tmpout"
    ch=$(echo "$body" | jq -r '.channels')
    assert_eq "$ch" "2" "pan output channels=2" || return 1
    echo "OK: pan_output_stereo"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_pan_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "position=0.0" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pan")
    assert_eq "$code" "200" "pan mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: pan_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── position out of range → 400 ───────────────────────────────────────────────

test_pan_out_of_range_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "position=2.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pan")
    assert_eq "$code" "400" "position=2.0 -> 400" || return 1
    echo "OK: pan_out_of_range_400"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_pan_missing_file_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pan")
    assert_eq "$code" "400" "missing file -> 400" || return 1
    echo "OK: pan_missing_file_400"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_pan_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "position=-0.5" \
        -F "output_path=pan/left.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pan")
    if ! echo "$body" | jq -e '.path == "pan/left.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/pan/left.wav")
    assert_eq "$code" "200" "GET staged pan -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: pan_output_path"
}

harness_run_tests \
    test_pan_center \
    test_pan_hard_left \
    test_pan_hard_right \
    test_pan_output_stereo \
    test_pan_output_format_mp3 \
    test_pan_out_of_range_400 \
    test_pan_missing_file_400 \
    test_pan_output_path
