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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"target_key\":\"C\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "key-match -> 200" || { rm -f "$tmpout"; return 1; }
    if [ "$(stat -c%s "$tmpout")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: key_match_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── output_path returns JSON with source_key, target_key, semitones ───────────

test_key_match_json_metadata() {
    local body src_key tgt_key semitones
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"target_key\":\"G\",\"output_path\":\"key/matched.wav\"}" \
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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"target_key\":\"F#\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "target_key=F# -> 200" || return 1
    echo "OK: key_match_sharp_key"
}

test_key_match_flat_key() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"target_key\":\"Bb\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "target_key=Bb -> 200" || return 1
    echo "OK: key_match_flat_key"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_key_match_output_format_mp3() {
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
        -d "{\"file_path\":\"$_stage\",\"target_key\":\"A\",\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"target_key\":\"Z\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "400" "invalid key -> 400" || return 1
    echo "OK: key_match_invalid_key_400"
}

# ── target_key missing → 422 ─────────────────────────────────────────────────

test_key_match_missing_key_422() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "422" "missing target_key -> 422" || return 1
    echo "OK: key_match_missing_key_422"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_key_match_missing_file_404() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"file_path\":\"no/such.wav\",\"target_key\":\"C\"}" -o "/dev/null" -w "%{http_code}" --max-time 30 "${AUDIOLLA_BASE_URL}/v1/audio/key-match")
    [[ "$code" = "400" || "$code" = "404" || "$code" = "422" ]] || { echo "  FAIL: missing file -> got $code"; return 1; }
    echo "OK: key_match_missing_file_404 (code=$code)"
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
