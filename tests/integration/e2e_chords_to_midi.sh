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
        "${AUDIOLLA_BASE_URL}/v1/audio/chords-to-midi")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "chords-to-midi -> 200" || { rm -f "$tmpf"; return 1; }
    if [ "$(stat -c%s "$tmpf")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"; rm -f "$tmpf"; return 1
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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"ctm_test/chords.mid\"}" \
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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"octave\":5,\"velocity\":100,\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/chords-to-midi")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "chords-to-midi octave=5 -> 200" || { rm -f "$tmpf"; return 1; }
    rm -f "$tmpf"
    echo "OK: chords_to_midi_custom_octave"
}

# ── invalid velocity → 400 ────────────────────────────────────────────────────

test_chords_to_midi_invalid_velocity() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"velocity\":200,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/chords-to-midi")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] && echo "  OK: $velocity=200 -> 422 (code=$code)" || { echo "  FAIL: $velocity=200 -> 422 expected 400 or 422, got $code"; return 1; } || return 1
    echo "OK: chords_to_midi_invalid_velocity"
}

harness_run_tests \
    test_chords_to_midi_returns_midi \
    test_chords_to_midi_staged_response \
    test_chords_to_midi_custom_octave \
    test_chords_to_midi_invalid_velocity
