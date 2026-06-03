#!/bin/bash
# Key match — /v1/audio/key-match end-to-end.
#
#     bash tests/integration/e2e_key_match.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "chord-detect,stretch"

# ── basic request → 200 WAV ───────────────────────────────────────────────────

test_key_match_returns_wav() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 180 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_key=C" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    assert_eq "$code" "200" "key-match -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: key_match_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── output_path returns JSON with source_key, target_key, semitones ───────────

test_key_match_json_metadata() {
    local body src_key tgt_key semitones
    body=$(curl -s --max-time 180 -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_key=G" \
        -F "output_path=key/matched.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    src_key=$(echo "$body" | jq -r '.source_key // empty')
    tgt_key=$(echo "$body" | jq -r '.target_key // empty')
    semitones=$(echo "$body" | jq -r '.semitones // "MISSING"')
    if [ -z "$src_key" ] || [ -z "$tgt_key" ]; then
        echo "  FAIL: missing key metadata; body: $body"; return 1
    fi
    if [ "$semitones" = "MISSING" ]; then
        echo "  FAIL: missing semitones field; body: $body"; return 1
    fi
    echo "OK: key_match_json_metadata (source=${src_key} target=${tgt_key} semitones=${semitones})"
}

# ── sharp and flat target keys accepted ───────────────────────────────────────

test_key_match_sharp_key() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 180 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_key=F#" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    assert_eq "$code" "200" "target_key=F# -> 200" || return 1
    echo "OK: key_match_sharp_key"
}

test_key_match_flat_key() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 180 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_key=Bb" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    assert_eq "$code" "200" "target_key=Bb -> 200" || return 1
    echo "OK: key_match_flat_key"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_key_match_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 180 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_key=A" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    assert_eq "$code" "200" "key-match mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: key_match_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── invalid target_key → 400 ─────────────────────────────────────────────────

test_key_match_invalid_key_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_key=Z" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    assert_eq "$code" "400" "invalid key -> 400" || return 1
    echo "OK: key_match_invalid_key_400"
}

# ── target_key missing → 422 ─────────────────────────────────────────────────

test_key_match_missing_key_422() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    assert_eq "$code" "422" "missing target_key -> 422" || return 1
    echo "OK: key_match_missing_key_422"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_key_match_missing_file_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        -F "target_key=C" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: key_match_missing_file_404"
}

harness_run_tests \
    test_key_match_returns_wav \
    test_key_match_json_metadata \
    test_key_match_sharp_key \
    test_key_match_flat_key \
    test_key_match_output_format_mp3 \
    test_key_match_invalid_key_400 \
    test_key_match_missing_key_422 \
    test_key_match_missing_file_404
