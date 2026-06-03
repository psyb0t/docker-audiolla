#!/bin/bash
# Audio fade — /v1/audio/fade end-to-end.
#
#     bash tests/integration/e2e_fade.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── fade_in only → 200 WAV ────────────────────────────────────────────────────

test_fade_in_returns_wav() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "fade_in=1.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fade")
    assert_eq "$code" "200" "fade_in -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: fade_in_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── fade_out only → 200 ───────────────────────────────────────────────────────

test_fade_out_only() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "fade_out=2.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fade")
    assert_eq "$code" "200" "fade_out -> 200" || return 1
    echo "OK: fade_out_only"
}

# ── both fade_in and fade_out → 200 ──────────────────────────────────────────

test_fade_both() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "fade_in=1.0" \
        -F "fade_out=1.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fade")
    assert_eq "$code" "200" "fade both -> 200" || return 1
    echo "OK: fade_both"
}

# ── custom curve accepted ─────────────────────────────────────────────────────

test_fade_custom_curve() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "fade_in=1.0" \
        -F "curve=qsin" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fade")
    assert_eq "$code" "200" "curve=qsin -> 200" || return 1
    echo "OK: fade_custom_curve"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_fade_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "fade_in=1.0" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fade")
    assert_eq "$code" "200" "fade mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: fade_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── neither fade_in nor fade_out → 400 ───────────────────────────────────────

test_fade_neither_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fade")
    assert_eq "$code" "400" "neither fade -> 400" || return 1
    echo "OK: fade_neither_400"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_fade_missing_file_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        -F "fade_in=1.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fade")
    assert_eq "$code" "400" "missing file -> 400" || return 1
    echo "OK: fade_missing_file_400"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_fade_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "fade_in=1.0" \
        -F "fade_out=1.0" \
        -F "output_path=fade/out.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fade")
    if ! echo "$body" | jq -e '.path == "fade/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/fade/out.wav")
    assert_eq "$code" "200" "GET staged fade -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: fade_output_path"
}

harness_run_tests \
    test_fade_in_returns_wav \
    test_fade_out_only \
    test_fade_both \
    test_fade_custom_curve \
    test_fade_output_format_mp3 \
    test_fade_neither_400 \
    test_fade_missing_file_400 \
    test_fade_output_path
