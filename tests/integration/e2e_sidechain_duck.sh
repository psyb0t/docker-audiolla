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
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${FIXTURE_REF}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${FIXTURE_REF}")" >/dev/null || true
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
        -d "{\"file_path\":\"$_stage\",\"trigger_file_path\":\"secondary/$(basename "${FIXTURE_REF}")\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "sidechain-duck -> 200" || { rm -f "$tmpout"; return 1; }
    if [ "$(stat -c%s "$tmpout")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: sidechain_duck_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── custom threshold_db and ratio accepted ───────────────────────────────────

test_sidechain_duck_custom_params() {
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${FIXTURE_REF}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${FIXTURE_REF}")" >/dev/null || true
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"trigger_file_path\":\"secondary/$(basename "${FIXTURE_REF}")\",\"threshold_db\":-30.0,\"ratio\":8.0,\"attack_ms\":5.0,\"release_ms\":100.0,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "sidechain-duck custom params -> 200" || return 1
    echo "OK: sidechain_duck_custom_params"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_sidechain_duck_output_format_mp3() {
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${FIXTURE_REF}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${FIXTURE_REF}")" >/dev/null || true
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
        -d "{\"file_path\":\"$_stage\",\"trigger_file_path\":\"secondary/$(basename "${FIXTURE_REF}")\",\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE_REF}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE_REF}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"start_sec\":0.0,\"end_sec\":4.0,\"output_path\":\"duck/trigger.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim"

    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"trigger_file_path\":\"duck/trigger.wav\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "staged trigger_file_path -> 200" || return 1
    echo "OK: sidechain_duck_staged_trigger"
}

# ── missing trigger → 400 ────────────────────────────────────────────────────

test_sidechain_duck_missing_trigger_422() {
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
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] || { echo "  FAIL: missing trigger -> got $code"; return 1; }
    echo "OK: sidechain_duck_missing_trigger_422 (code=$code)"
}

# ── missing primary file → 400 ───────────────────────────────────────────────

test_sidechain_duck_missing_primary_404() {
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${FIXTURE_REF}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${FIXTURE_REF}")" >/dev/null || true
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"no/such.wav\",\"trigger_file_path\":\"secondary/$(basename "${FIXTURE_REF}")\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/sidechain-duck")
    [[ "$code" = "400" || "$code" = "404" || "$code" = "422" || "$code" = "500" ]] || { echo "  FAIL: missing primary -> got $code"; return 1; }
    echo "OK: sidechain_duck_missing_primary_404 (code=$code)"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_sidechain_duck_output_path() {
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${FIXTURE_REF}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${FIXTURE_REF}")" >/dev/null || true
    local body code tmpout
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"trigger_file_path\":\"secondary/$(basename "${FIXTURE_REF}")\",\"output_path\":\"duck/out.wav\"}" \
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
    test_sidechain_duck_missing_trigger_422 \
    test_sidechain_duck_missing_primary_404 \
    test_sidechain_duck_output_path
