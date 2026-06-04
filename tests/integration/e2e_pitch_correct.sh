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
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pitch-correct")
    assert_eq "$code" "200" "pitch-correct default -> 200" || { rm -f "$tmpf"; return 1; }
    if ! head -c 4 "$tmpf" | grep -q "RIFF"; then
        echo "  FAIL: output not WAV"; rm -f "$tmpf"; return 1
    fi
    rm -f "$tmpf"
    echo "OK: pitch_correct_returns_wav"
}

# ── strength=0 returns near-identical audio ───────────────────────────────────

test_pitch_correct_bypass() {
    local tmpf code
    tmpf=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "strength=0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pitch-correct")
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
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_path=pc_test/corrected.wav" \
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
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "strength=2.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/pitch-correct")
    assert_eq "$code" "400" "strength=2.0 -> 400" || return 1
    echo "OK: pitch_correct_invalid_strength"
}

harness_run_tests \
    test_pitch_correct_returns_wav \
    test_pitch_correct_bypass \
    test_pitch_correct_output_path \
    test_pitch_correct_invalid_strength
