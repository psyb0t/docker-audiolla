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

ONE_BAND='[{"freq":1000,"gain_db":3.0,"width_hz":100}]'
TWO_BANDS='[{"freq":200,"gain_db":-6.0,"width_hz":50},{"freq":8000,"gain_db":6.0,"width_hz":500}]'

# ── single band → 200 WAV ────────────────────────────────────────────────────

test_eq_returns_wav() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "bands=${ONE_BAND}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "200" "eq -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: eq_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── multiple bands accepted ────────────────────────────────────────────────────

test_eq_multiple_bands() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "bands=${TWO_BANDS}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "200" "eq two bands -> 200" || return 1
    echo "OK: eq_multiple_bands"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_eq_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "bands=${ONE_BAND}" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "200" "eq mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: eq_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── invalid JSON bands → 400 ─────────────────────────────────────────────────

test_eq_invalid_bands_json_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "bands=not-json" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "400" "invalid bands JSON -> 400" || return 1
    echo "OK: eq_invalid_bands_json_400"
}

# ── bands missing → 422 ───────────────────────────────────────────────────────

test_eq_missing_bands_422() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "422" "missing bands -> 422" || return 1
    echo "OK: eq_missing_bands_422"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_eq_missing_file_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        -F "bands=${ONE_BAND}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/eq")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: eq_missing_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_eq_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "bands=${ONE_BAND}" \
        -F "output_path=eq/out.wav" \
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
