#!/bin/bash
# Chords to MIDI — /v1/audio/chords-to-midi.
#
#     bash tests/integration/e2e_chords_to_midi.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze,chord-detect"

# ── returns MIDI file ─────────────────────────────────────────────────────────

test_chords_to_midi_returns_midi() {
    local tmpf code
    tmpf=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 90 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/chords-to-midi")
    assert_eq "$code" "200" "chords-to-midi -> 200" || { rm -f "$tmpf"; return 1; }
    if ! head -c 4 "$tmpf" | grep -q "MThd"; then
        echo "  FAIL: output not MIDI"; rm -f "$tmpf"; return 1
    fi
    local sz
    sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    if [ "$sz" -lt 50 ]; then
        echo "  FAIL: MIDI too small ($sz bytes)"; return 1
    fi
    echo "OK: chords_to_midi_returns_midi (${sz}B)"
}

# ── JSON response includes key + chord_count ─────────────────────────────────

test_chords_to_midi_staged_response() {
    local body
    body=$(curl -s --max-time 90 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_path=ctm_test/chords.mid" \
        "${AUDIOLLA_BASE_URL}/v1/audio/chords-to-midi")
    if ! echo "$body" | jq -e '.path == "ctm_test/chords.mid"' >/dev/null 2>&1; then
        echo "  FAIL: path missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.chord_count > 0' >/dev/null 2>&1; then
        echo "  FAIL: chord_count missing or zero; body: $body"; return 1
    fi
    echo "OK: chords_to_midi_staged_response"
}

# ── custom octave accepted ─────────────────────────────────────────────────────

test_chords_to_midi_custom_octave() {
    local tmpf code
    tmpf=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 90 -X POST \
        -F "file=@${FIXTURE}" \
        -F "octave=5" \
        -F "velocity=100" \
        "${AUDIOLLA_BASE_URL}/v1/audio/chords-to-midi")
    assert_eq "$code" "200" "chords-to-midi octave=5 -> 200" || { rm -f "$tmpf"; return 1; }
    rm -f "$tmpf"
    echo "OK: chords_to_midi_custom_octave"
}

# ── invalid velocity → 400 ────────────────────────────────────────────────────

test_chords_to_midi_invalid_velocity() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "velocity=200" \
        "${AUDIOLLA_BASE_URL}/v1/audio/chords-to-midi")
    assert_eq "$code" "400" "velocity=200 -> 400" || return 1
    echo "OK: chords_to_midi_invalid_velocity"
}

harness_run_tests \
    test_chords_to_midi_returns_midi \
    test_chords_to_midi_staged_response \
    test_chords_to_midi_custom_octave \
    test_chords_to_midi_invalid_velocity
