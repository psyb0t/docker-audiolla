#!/bin/bash
# Audio-to-MIDI transcription — /v1/audio/to_midi.
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

harness_start "basic-pitch"

# ── basic call: returns MIDI bytes ───────────────────────────────────────────

test_to_midi_returns_midi_bytes() {
    local code tmp
    tmp=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/to_midi")
    assert_eq "$code" "200" "to_midi -> 200" || { rm -f "$tmp"; return 1; }

    local ct
    ct=$(curl -s -o /dev/null -w "%{content_type}" --max-time 30 \
        -X POST -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/to_midi")
    if ! echo "$ct" | grep -qi "midi"; then
        echo "  FAIL: Content-Type not midi: $ct"
        rm -f "$tmp"; return 1
    fi

    if ! head -c 4 "$tmp" | grep -q "MThd"; then
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

# ── custom onset_threshold still works ───────────────────────────────────────

test_to_midi_custom_onset_threshold() {
    local code tmp
    tmp=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "onset_threshold=0.8" \
        "${AUDIOLLA_BASE_URL}/v1/audio/to_midi")
    assert_eq "$code" "200" "to_midi onset_threshold=0.8 -> 200" || { rm -f "$tmp"; return 1; }
    if ! head -c 4 "$tmp" | grep -q "MThd"; then
        echo "  FAIL: response not MIDI"; rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: to_midi_custom_onset_threshold"
}

# ── output_path: writes MIDI to staging ──────────────────────────────────────

test_to_midi_output_path() {
    local body code fetched
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_path=midi/transcribed.mid" \
        "${AUDIOLLA_BASE_URL}/v1/audio/to_midi")
    if ! echo "$body" | jq -e '.path == "midi/transcribed.mid"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.mid)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/midi/transcribed.mid")
    assert_eq "$code" "200" "GET staged MIDI -> 200" || { rm -f "$fetched"; return 1; }
    if ! head -c 4 "$fetched" | grep -q "MThd"; then
        echo "  FAIL: staged file not MIDI"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: to_midi_output_path (staged)"
}

# ── deterministic: same audio produces the same fingerprint ──────────────────

test_to_midi_is_deterministic() {
    local m1 m2
    m1=$(mktemp --suffix=.mid)
    m2=$(mktemp --suffix=.mid)
    curl -s -o "$m1" --max-time 120 -X POST \
        -F "file=@${FIXTURE}" "${AUDIOLLA_BASE_URL}/v1/audio/to_midi"
    curl -s -o "$m2" --max-time 120 -X POST \
        -F "file=@${FIXTURE}" "${AUDIOLLA_BASE_URL}/v1/audio/to_midi"
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

# ── wrong engine type → 400 ───────────────────────────────────────────────────

test_to_midi_rejects_non_pitch_engine() {
    local code body
    body=$(curl -s -o /tmp/audiolla-midi.$$ -w "%{http_code}" \
        --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=silence-detect" \
        "${AUDIOLLA_BASE_URL}/v1/audio/to_midi")
    code="$body"
    body=$(cat /tmp/audiolla-midi.$$ 2>/dev/null)
    rm -f /tmp/audiolla-midi.$$
    # silence-detect not enabled in this harness, so expect 404.
    if [ "$code" != "400" ] && [ "$code" != "404" ]; then
        echo "  FAIL: wrong engine type -> expected 400 or 404, got $code; body: $body"
        return 1
    fi
    echo "OK: to_midi_rejects_non_pitch_engine ($code)"
}

harness_run_tests \
    test_to_midi_returns_midi_bytes \
    test_to_midi_custom_onset_threshold \
    test_to_midi_output_path \
    test_to_midi_is_deterministic \
    test_to_midi_rejects_non_pitch_engine
