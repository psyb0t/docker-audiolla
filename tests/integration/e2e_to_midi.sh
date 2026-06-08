#!/bin/bash
# Audio-to-MIDI transcription — /v1/audio/to_midi/{engine}.
# basic-pitch (ONNX backend) is installed in the prod image.
#
#     bash tests/integration/e2e_to_midi.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"
ENGINE="basic-pitch"
URL="${AUDIOLLA_BASE_URL}/v1/audio/to_midi/${ENGINE}"

harness_start "basic-pitch"

# ── basic call: returns MIDI bytes ───────────────────────────────────────────

test_to_midi_returns_midi_bytes() {
    local code tmp
    tmp=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${URL}")
    assert_eq "$code" "200" "to_midi -> 200" || { rm -f "$tmp"; return 1; }

    local ct
    ct=$(curl -s -o /dev/null -w "%{content_type}" --max-time 120 \
        -X POST -F "file=@${FIXTURE}" "${URL}")
    if ! echo "$ct" | grep -qi "midi"; then
        echo "  FAIL: Content-Type not midi: $ct"
        rm -f "$tmp"; return 1
    fi

    if ! [ -s "$tmp" ]; then
        echo "  FAIL: response is not a valid MIDI file"
        rm -f "$tmp"; return 1
    fi
    local size
    size=$(stat -c%s "$tmp")
    rm -f "$tmp"
    if [ "$size" -lt 10 ]; then
        echo "  FAIL: MIDI output suspiciously small ($size bytes)"; return 1
    fi
    echo "OK: to_midi_returns_midi_bytes ($size bytes)"
}

# ── onset_threshold param ────────────────────────────────────────────────────

test_to_midi_onset_threshold() {
    local code tmp
    tmp=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "onset_threshold=0.8" \
        "${URL}")
    assert_eq "$code" "200" "onset_threshold=0.8 -> 200" || { rm -f "$tmp"; return 1; }
    [ -s "$tmp" ] || { echo "  FAIL: not MIDI"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: to_midi_onset_threshold"
}

# ── frame_threshold param ────────────────────────────────────────────────────

test_to_midi_frame_threshold() {
    local code tmp
    tmp=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "frame_threshold=0.2" \
        "${URL}")
    assert_eq "$code" "200" "frame_threshold=0.2 -> 200" || { rm -f "$tmp"; return 1; }
    [ -s "$tmp" ] || { echo "  FAIL: not MIDI"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: to_midi_frame_threshold"
}

# ── minimum_note_length_ms param ─────────────────────────────────────────────

test_to_midi_minimum_note_length_ms() {
    local code tmp
    tmp=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "minimum_note_length_ms=120" \
        "${URL}")
    assert_eq "$code" "200" "minimum_note_length_ms=120 -> 200" || { rm -f "$tmp"; return 1; }
    [ -s "$tmp" ] || { echo "  FAIL: not MIDI"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: to_midi_minimum_note_length_ms"
}

# ── minimum_frequency + maximum_frequency ────────────────────────────────────

test_to_midi_frequency_range() {
    local code tmp
    tmp=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "minimum_frequency=100" \
        -F "maximum_frequency=2000" \
        "${URL}")
    assert_eq "$code" "200" "frequency_range -> 200" || { rm -f "$tmp"; return 1; }
    [ -s "$tmp" ] || { echo "  FAIL: not MIDI"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: to_midi_frequency_range"
}

# ── multiple_pitch_bends param ────────────────────────────────────────────────

test_to_midi_multiple_pitch_bends() {
    local code tmp
    tmp=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "multiple_pitch_bends=true" \
        "${URL}")
    assert_eq "$code" "200" "multiple_pitch_bends=true -> 200" || { rm -f "$tmp"; return 1; }
    [ -s "$tmp" ] || { echo "  FAIL: not MIDI"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: to_midi_multiple_pitch_bends"
}

# ── melodia_trick=false ────────────────────────────────────────────────────────

test_to_midi_melodia_trick_false() {
    local code tmp
    tmp=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "melodia_trick=false" \
        "${URL}")
    assert_eq "$code" "200" "melodia_trick=false -> 200" || { rm -f "$tmp"; return 1; }
    [ -s "$tmp" ] || { echo "  FAIL: not MIDI"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: to_midi_melodia_trick_false"
}

# ── output_path: writes MIDI to staging ──────────────────────────────────────

test_to_midi_output_path() {
    local body code fetched
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_path=midi/transcribed.mid" \
        "${URL}")
    if ! echo "$body" | jq -e '.path == "midi/transcribed.mid"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/midi/transcribed.mid")
    assert_eq "$code" "200" "GET staged MIDI -> 200" || { rm -f "$fetched"; return 1; }
    jq -e .path $fetched >/dev/null 2>&1 || { echo "  FAIL: staged not MIDI"; rm -f "$fetched"; return 1; }
    rm -f "$fetched"
    echo "OK: to_midi_output_path"
}

# ── deterministic: same audio → same size output ─────────────────────────────

test_to_midi_is_deterministic() {
    local m1 m2
    m1=$(mktemp --suffix=.mid)
    m2=$(mktemp --suffix=.mid)
    curl -s -o "$m1" --max-time 120 -X POST -F "file=@${FIXTURE}" "${URL}"
    curl -s -o "$m2" --max-time 120 -X POST -F "file=@${FIXTURE}" "${URL}"
    local sz1 sz2
    sz1=$(stat -c%s "$m1")
    sz2=$(stat -c%s "$m2")
    rm -f "$m1" "$m2"
    if [ "$sz1" != "$sz2" ]; then
        echo "  FAIL: sizes differ on identical inputs ($sz1 vs $sz2)"
        return 1
    fi
    echo "OK: to_midi_is_deterministic (both $sz1 bytes)"
}

# ── wrong engine slug → 400 ──────────────────────────────────────────────────

test_to_midi_wrong_engine_type() {
    local code body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/tmp/audiolla-midi.$$" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/to_midi/silence-detect")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/tmp/audiolla-midi.$$" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    code="$body"
    body=$(cat /tmp/audiolla-midi.$$ 2>/dev/null)
    rm -f /tmp/audiolla-midi.$$
    if [ "$code" != "400" ] && [ "$code" != "404" ]; then
        echo "  FAIL: wrong engine -> expected 400 or 404, got $code; body: $body"
        return 1
    fi
    echo "OK: to_midi_wrong_engine_type ($code)"
}

harness_run_tests \
    test_to_midi_returns_midi_bytes \
    test_to_midi_onset_threshold \
    test_to_midi_frame_threshold \
    test_to_midi_minimum_note_length_ms \
    test_to_midi_frequency_range \
    test_to_midi_multiple_pitch_bends \
    test_to_midi_melodia_trick_false \
    test_to_midi_output_path \
    test_to_midi_is_deterministic \
    test_to_midi_wrong_engine_type
