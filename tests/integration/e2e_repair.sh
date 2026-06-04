#!/bin/bash
# Audio repair (declip + dehum) — /v1/audio/repair.
#
#     bash tests/integration/e2e_repair.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── declip default returns WAV ────────────────────────────────────────────────

test_repair_declip_returns_wav() {
    local tmpf code
    tmpf=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/repair")
    assert_eq "$code" "200" "repair declip -> 200" || { rm -f "$tmpf"; return 1; }
    if ! head -c 4 "$tmpf" | grep -q "RIFF"; then
        echo "  FAIL: output not WAV"; rm -f "$tmpf"; return 1
    fi
    rm -f "$tmpf"
    echo "OK: repair_declip_returns_wav"
}

# ── dehum returns same-size audio ────────────────────────────────────────────

test_repair_dehum() {
    local tmpf code
    tmpf=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "declip=false" \
        -F "dehum=true" \
        -F "hum_freq=50" \
        "${AUDIOLLA_BASE_URL}/v1/audio/repair")
    assert_eq "$code" "200" "repair dehum -> 200" || { rm -f "$tmpf"; return 1; }
    local in_sz out_sz diff bound
    in_sz=$(stat -c%s "$FIXTURE")
    out_sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    diff=$(( out_sz - in_sz ))
    bound=$(( in_sz / 10 ))
    if [ "$diff" -lt "-$bound" ] || [ "$diff" -gt "$bound" ]; then
        echo "  FAIL: output size too different (in=$in_sz out=$out_sz)"; return 1
    fi
    echo "OK: repair_dehum (in=$in_sz out=$out_sz)"
}

# ── output_path stages result ─────────────────────────────────────────────────

test_repair_output_path() {
    local body code fetched
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_path=repair_test/fixed.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/repair")
    if ! echo "$body" | jq -e '.path == "repair_test/fixed.wav"' >/dev/null 2>&1; then
        echo "  FAIL: path missing; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/repair_test/fixed.wav")
    assert_eq "$code" "200" "GET staged repair -> 200" || { rm -f "$fetched"; return 1; }
    rm -f "$fetched"
    echo "OK: repair_output_path"
}

# ── both false → 400 ─────────────────────────────────────────────────────────

test_repair_both_false_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "declip=false" \
        -F "dehum=false" \
        "${AUDIOLLA_BASE_URL}/v1/audio/repair")
    assert_eq "$code" "400" "declip=false dehum=false -> 400" || return 1
    echo "OK: repair_both_false_400"
}

harness_run_tests \
    test_repair_declip_returns_wav \
    test_repair_dehum \
    test_repair_output_path \
    test_repair_both_false_400
