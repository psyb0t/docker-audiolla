#!/bin/bash
# Chromaprint audio fingerprint — /v1/audio/fingerprint.
#
#     bash tests/integration/e2e_fingerprint.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "audio-fingerprint"

# ── compute: returns duration + base64 fingerprint string ───────────────────

test_fingerprint_returns_string() {
    local body
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fingerprint")
    if ! echo "$body" | jq -e '.duration | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: duration not a number; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.fingerprint | type == "string" and length > 20' >/dev/null 2>&1; then
        echo "  FAIL: fingerprint not a non-trivial string; body: $body"; return 1
    fi
    echo "OK: fingerprint_returns_string (duration=$(echo "$body" | jq -r '.duration'))"
}

# ── deterministic: same input → same fingerprint ────────────────────────────

test_fingerprint_is_deterministic() {
    local b1 b2 fp1 fp2
    b1=$(curl -s --max-time 60 -X POST -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fingerprint")
    b2=$(curl -s --max-time 60 -X POST -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fingerprint")
    fp1=$(echo "$b1" | jq -r '.fingerprint')
    fp2=$(echo "$b2" | jq -r '.fingerprint')
    if [ "$fp1" != "$fp2" ]; then
        echo "  FAIL: fingerprints differ across identical calls"
        return 1
    fi
    echo "OK: fingerprint_is_deterministic"
}

# ── return_raw: adds the integer array ──────────────────────────────────────

test_fingerprint_return_raw() {
    local body
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "return_raw=true" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fingerprint")
    if ! echo "$body" | jq -e '.fingerprint_raw | type == "array" and length > 0' >/dev/null 2>&1; then
        echo "  FAIL: fingerprint_raw missing or empty; body: $(echo "$body" | head -c 500)"
        return 1
    fi
    # The first element should be an integer (chromaprint hashes are 32-bit).
    if ! echo "$body" | jq -e '.fingerprint_raw[0] | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: raw fingerprint entries are not numbers"
        return 1
    fi
    echo "OK: fingerprint_return_raw ($(echo "$body" | jq -r '.fingerprint_raw | length') ints)"
}

# ── file_path: feed a staged file ───────────────────────────────────────────

test_fingerprint_via_file_path() {
    local code body
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X PUT --data-binary "@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/files/fp/in.wav")
    if [ "$code" != "201" ]; then
        echo "  FAIL: stage fixture -> $code"; return 1
    fi
    body=$(curl -s --max-time 60 -X POST \
        -F "file_path=fp/in.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fingerprint")
    if ! echo "$body" | jq -e '.fingerprint | type == "string"' >/dev/null 2>&1; then
        echo "  FAIL: fingerprint missing for staged file; body: $body"; return 1
    fi
    echo "OK: fingerprint_via_file_path"
}

# ── analyze_seconds: limits how many seconds fpcalc scans ───────────────────

test_fingerprint_analyze_seconds() {
    local body_full body_short fp_full fp_short
    # Default (120s) — covers the entire 8s fixture so both should match.
    body_full=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fingerprint")
    body_short=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "analyze_seconds=3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fingerprint")
    if ! echo "$body_short" | jq -e '.fingerprint | type == "string" and length > 0' >/dev/null 2>&1; then
        echo "  FAIL: fingerprint missing with analyze_seconds=3; body: $body_short"; return 1
    fi
    # A 3s window produces a shorter (or equal) fingerprint than full scan.
    fp_full=$(echo "$body_full"  | jq -r '.fingerprint | length')
    fp_short=$(echo "$body_short" | jq -r '.fingerprint | length')
    if [ "$fp_short" -gt "$fp_full" ]; then
        echo "  FAIL: shorter window produced a longer fingerprint ($fp_short > $fp_full)"
        return 1
    fi
    echo "OK: fingerprint_analyze_seconds (full=${fp_full} short=${fp_short} chars)"
}

harness_run_tests \
    test_fingerprint_returns_string \
    test_fingerprint_is_deterministic \
    test_fingerprint_return_raw \
    test_fingerprint_via_file_path \
    test_fingerprint_analyze_seconds
