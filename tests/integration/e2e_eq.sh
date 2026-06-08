#!/bin/bash
# Parametric EQ — /v1/audio/eq end-to-end.
#
#     bash tests/integration/e2e_eq.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# v1.0.0: bands is a JSON array embedded directly in the request body —
# NOT a string. The schema declares `bands: array<object>`.
ONE_BAND='[{"freq":1000,"gain_db":3.0,"width_hz":100}]'
TWO_BANDS='[{"freq":200,"gain_db":-6.0,"width_hz":50},{"freq":8000,"gain_db":6.0,"width_hz":500}]'

# ── single band → 200 + valid WAV staged ─────────────────────────────────────

test_eq_returns_wav() {
    local code body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/eq-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(mktemp)
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"bands\":${ONE_BAND},\"output_path\":\"$_out\"}" \
        -o "$body" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "200" "eq -> 200" || { rm -f "$body"; return 1; }
    rm -f "$body"
    # Verify the staged output exists and is non-trivial
    local fetched
    fetched=$(mktemp)
    curl -sf -o "$fetched" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: could not fetch staged output"; rm -f "$fetched"; return 1
    }
    if [ "$(stat -c%s "$fetched")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$fetched"; return 1
    fi
    echo "OK: eq_returns_wav ($(stat -c%s "$fetched") bytes)"
    rm -f "$fetched"
}

# ── multiple bands accepted ───────────────────────────────────────────────────

test_eq_multiple_bands() {
    local code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/eq2-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"bands\":${TWO_BANDS},\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "200" "eq two bands -> 200" || return 1
    echo "OK: eq_multiple_bands"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_eq_output_format_mp3() {
    local code body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/eq-$$-$RANDOM.mp3"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(mktemp)
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"bands\":${ONE_BAND},\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$body" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "200" "eq mp3 -> 200" || { rm -f "$body"; return 1; }
    rm -f "$body"
    local fetched
    fetched=$(mktemp)
    curl -sf -o "$fetched" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: could not fetch staged mp3"; rm -f "$fetched"; return 1
    }
    if [ ! -s "$fetched" ]; then
        echo "  FAIL: empty mp3"; rm -f "$fetched"; return 1
    fi
    echo "OK: eq_output_format_mp3 ($(stat -c%s "$fetched") bytes)"
    rm -f "$fetched"
}

# ── invalid bands type (string instead of array) → 422 (Pydantic) ────────────

test_eq_invalid_bands_json_400() {
    local code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/eq-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"bands\":\"not-json\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "422" "invalid bands -> 422" || return 1
    echo "OK: eq_invalid_bands_json_400"
}

# ── bands missing → 422 ───────────────────────────────────────────────────────

test_eq_missing_bands_422() {
    local code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/eq-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "422" "missing bands -> 422" || return 1
    echo "OK: eq_missing_bands_422"
}

# ── missing file → 404 (with output_path → handler-level) ─────────────────────

test_eq_missing_file_404() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"no/such.wav\",\"bands\":${ONE_BAND},\"output_path\":\"out/eq-missing-$$.wav\"}" \
        -o "/dev/null" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: eq_missing_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_eq_output_path() {
    local body code tmpout
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"bands\":${ONE_BAND},\"output_path\":\"eq/out.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    if ! echo "$body" | jq -e '.path == "eq/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/eq/out.wav")
    assert_eq "$code" "200" "GET staged eq -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: eq_output_path"
}

harness_run_tests \
    test_eq_returns_wav \
    test_eq_multiple_bands \
    test_eq_output_format_mp3 \
    test_eq_invalid_bands_json_400 \
    test_eq_missing_bands_422 \
    test_eq_missing_file_404 \
    test_eq_output_path
