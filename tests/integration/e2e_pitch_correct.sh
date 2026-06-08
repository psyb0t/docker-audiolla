#!/bin/bash
# Pitch correction — /v1/audio/pitch-correct.
#
#     bash tests/integration/e2e_pitch_correct.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── default strength returns WAV ──────────────────────────────────────────────

test_pitch_correct_returns_wav() {
    local tmpf code
    tmpf=$(mktemp --suffix=.wav)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pitch-correct")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "pitch-correct default -> 200" || { rm -f "$tmpf"; return 1; }
    if [ "$(stat -c%s "$tmpf")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"; rm -f "$tmpf"; return 1
    fi
    rm -f "$tmpf"
    echo "OK: pitch_correct_returns_wav"
}

# ── strength=0 returns near-identical audio ───────────────────────────────────

test_pitch_correct_bypass() {
    local tmpf code
    tmpf=$(mktemp --suffix=.wav)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"strength\":0,\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pitch-correct")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "strength=0 -> 200" || { rm -f "$tmpf"; return 1; }
    local sz
    sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    local in_sz
    in_sz=$(stat -c%s "$FIXTURE")
    local diff
    diff=$(( sz - in_sz ))
    local bound
    bound=$(( in_sz / 10 ))
    if [ "$diff" -lt "-$bound" ] || [ "$diff" -gt "$bound" ]; then
        echo "  FAIL: bypass output size too different (in=$in_sz out=$sz)"; return 1
    fi
    echo "OK: pitch_correct_bypass (in=$in_sz out=$sz)"
}

# ── output_path stages result ─────────────────────────────────────────────────

test_pitch_correct_output_path() {
    local body code fetched
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"pc_test/corrected.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pitch-correct")
    if ! echo "$body" | jq -e '.path == "pc_test/corrected.wav"' >/dev/null 2>&1; then
        echo "  FAIL: path missing; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/pc_test/corrected.wav")
    assert_eq "$code" "200" "GET staged pitch-correct -> 200" || { rm -f "$fetched"; return 1; }
    rm -f "$fetched"
    echo "OK: pitch_correct_output_path"
}

# ── invalid strength → 400 ────────────────────────────────────────────────────

test_pitch_correct_invalid_strength() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"strength\":2.0,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pitch-correct")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] && echo "  OK: $strength=2.0 -> 422 (code=$code)" || { echo "  FAIL: $strength=2.0 -> 422 expected 400 or 422, got $code"; return 1; } || return 1
    echo "OK: pitch_correct_invalid_strength"
}

harness_run_tests \
    test_pitch_correct_returns_wav \
    test_pitch_correct_bypass \
    test_pitch_correct_output_path \
    test_pitch_correct_invalid_strength
