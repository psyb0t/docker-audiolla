#!/bin/bash
# Drum pattern synthesis — /v1/midi/drum.
#
#     bash tests/integration/e2e_drum.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

harness_start "midi-compose"

# ── basic 4/4 pattern returns MIDI ────────────────────────────────────────────

test_drum_basic_pattern() {
    local tmpf code
    tmpf=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 30 -X POST \
        -H "Content-Type: application/json" \
        -d '{"tempo_bpm":120,"steps":16,"bars":2,"pattern":{"kick":[1,0,0,0,1,0,0,0,1,0,0,0,1,0,0,0],"snare":[0,0,0,0,1,0,0,0,0,0,0,0,1,0,0,0],"hihat":[1,1,1,1,1,1,1,1,1,1,1,1,1,1,1,1]}}' \
        "${AUDIOLLA_BASE_URL}/v1/midi/drum")
    assert_eq "$code" "200" "drum basic pattern -> 200" || { rm -f "$tmpf"; return 1; }
    if ! head -c 4 "$tmpf" | grep -q "MThd"; then
        echo "  FAIL: output not MIDI"; rm -f "$tmpf"; return 1
    fi
    local sz
    sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    if [ "$sz" -lt 50 ]; then
        echo "  FAIL: MIDI too small ($sz bytes)"; return 1
    fi
    echo "OK: drum_basic_pattern (${sz}B)"
}

# ── output_path stages MIDI ───────────────────────────────────────────────────

test_drum_output_path() {
    local body code fetched
    body=$(curl -s --max-time 30 -X POST \
        -H "Content-Type: application/json" \
        -d '{"tempo_bpm":90,"steps":8,"pattern":{"kick":[1,0,1,0,1,0,1,0],"snare":[0,0,1,0,0,0,1,0]}}' \
        "${AUDIOLLA_BASE_URL}/v1/midi/drum?output_path=drum_test%2Fbeat.mid")
    if ! echo "$body" | jq -e '.path == "drum_test/beat.mid"' >/dev/null 2>&1; then
        echo "  FAIL: path missing; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/drum_test/beat.mid")
    assert_eq "$code" "200" "GET staged drum MIDI -> 200" || { rm -f "$fetched"; return 1; }
    rm -f "$fetched"
    echo "OK: drum_output_path"
}

# ── swing parameter accepted ──────────────────────────────────────────────────

test_drum_swing() {
    local tmpf code
    tmpf=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 30 -X POST \
        -H "Content-Type: application/json" \
        -d '{"tempo_bpm":95,"swing":0.3,"steps":8,"pattern":{"kick":[1,0,0,0,1,0,0,0],"hihat":[1,1,1,1,1,1,1,1]}}' \
        "${AUDIOLLA_BASE_URL}/v1/midi/drum")
    assert_eq "$code" "200" "drum with swing -> 200" || { rm -f "$tmpf"; return 1; }
    rm -f "$tmpf"
    echo "OK: drum_swing"
}

# ── missing pattern → 400 ─────────────────────────────────────────────────────

test_drum_missing_pattern_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -H "Content-Type: application/json" \
        -d '{"tempo_bpm":120,"steps":16}' \
        "${AUDIOLLA_BASE_URL}/v1/midi/drum")
    assert_eq "$code" "400" "missing pattern -> 400" || return 1
    echo "OK: drum_missing_pattern_400"
}

harness_run_tests \
    test_drum_basic_pattern \
    test_drum_output_path \
    test_drum_swing \
    test_drum_missing_pattern_400
