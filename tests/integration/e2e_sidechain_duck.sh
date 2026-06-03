#!/bin/bash
# Sidechain duck — /v1/audio/sidechain-duck end-to-end.
#
#     bash tests/integration/e2e_sidechain_duck.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"
FIXTURE_REF="${_DIR}/.fixtures/audio_ref.wav"

harness_start "librosa-analyze"

# ── primary + trigger → 200 WAV ──────────────────────────────────────────────

test_sidechain_duck_returns_wav() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "trigger_file=@${FIXTURE_REF}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    assert_eq "$code" "200" "sidechain-duck -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: sidechain_duck_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── custom threshold_db and ratio accepted ───────────────────────────────────

test_sidechain_duck_custom_params() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "trigger_file=@${FIXTURE_REF}" \
        -F "threshold_db=-30.0" \
        -F "ratio=8.0" \
        -F "attack_ms=5.0" \
        -F "release_ms=100.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    assert_eq "$code" "200" "sidechain-duck custom params -> 200" || return 1
    echo "OK: sidechain_duck_custom_params"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_sidechain_duck_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "trigger_file=@${FIXTURE_REF}" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    assert_eq "$code" "200" "sidechain-duck mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: sidechain_duck_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── staged trigger file (trigger_file_path) accepted ─────────────────────────

test_sidechain_duck_staged_trigger() {
    # Stage trigger via trim
    curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE_REF}" \
        -F "start_sec=0.0" -F "end_sec=4.0" \
        -F "output_path=duck/trigger.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim" > /dev/null || return 1

    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "trigger_file_path=duck/trigger.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    assert_eq "$code" "200" "staged trigger_file_path -> 200" || return 1
    echo "OK: sidechain_duck_staged_trigger"
}

# ── missing trigger → 400 ────────────────────────────────────────────────────

test_sidechain_duck_missing_trigger_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    assert_eq "$code" "400" "missing trigger -> 400" || return 1
    echo "OK: sidechain_duck_missing_trigger_400"
}

# ── missing primary file → 400 ───────────────────────────────────────────────

test_sidechain_duck_missing_primary_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        -F "trigger_file=@${FIXTURE_REF}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    assert_eq "$code" "404" "missing primary -> 404" || return 1
    echo "OK: sidechain_duck_missing_primary_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_sidechain_duck_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "trigger_file=@${FIXTURE_REF}" \
        -F "output_path=duck/out.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    if ! echo "$body" | jq -e '.path == "duck/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/duck/out.wav")
    assert_eq "$code" "200" "GET staged duck -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: sidechain_duck_output_path"
}

harness_run_tests \
    test_sidechain_duck_returns_wav \
    test_sidechain_duck_custom_params \
    test_sidechain_duck_output_format_mp3 \
    test_sidechain_duck_staged_trigger \
    test_sidechain_duck_missing_trigger_400 \
    test_sidechain_duck_missing_primary_404 \
    test_sidechain_duck_output_path
