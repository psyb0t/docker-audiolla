#!/bin/bash
# MIDI quantize — /v1/midi/quantize end-to-end.
#
#     bash tests/integration/e2e_midi_quantize.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

harness_start "midi-compose"

# Minimal MIDI spec used throughout — C major arpeggio at 120 BPM.
SPEC='{
  "tempo_bpm": 120,
  "time_signature": [4, 4],
  "tracks": [
    {"name": "Lead", "program": 0, "channel": 0, "notes": [
      {"pitch": 60, "start_beats": 0.0, "duration_beats": 0.5, "velocity": 100},
      {"pitch": 64, "start_beats": 0.5, "duration_beats": 0.5, "velocity": 100},
      {"pitch": 67, "start_beats": 1.0, "duration_beats": 0.5, "velocity": 100}
    ]}
  ]
}'

_build_midi() {
    local out="$1"
    local code
    code=$(curl -s -o "$out" -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        --data "$SPEC" \
        "${AUDIOLLA_BASE_URL}/v1/midi/compose")
    if [ "$code" != "200" ]; then
        echo "  FAIL: pre-test compose failed -> $code"
        return 1
    fi
}

# ── default grid_beats=0.25 → returns MIDI ───────────────────────────────────

test_quantize_returns_midi() {
    local mid out code
    mid=$(mktemp --suffix=.mid)
    _build_midi "$mid" || { rm -f "$mid"; return 1; }
    out=$(mktemp)
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.mid"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o /dev/null \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/quantize")
    rm -f "$mid"
    assert_eq "$code" "200" "quantize -> 200" || { rm -f "$out"; return 1; }
    curl -sf -o "$out" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: GET staged quantized failed"; rm -f "$out"; return 1
    }
    if [ "$(head -c 4 "$out")" != "MThd" ]; then
        echo "  FAIL: staged file is not MIDI (no MThd)"; rm -f "$out"; return 1
    fi
    echo "OK: quantize_returns_midi ($(stat -c%s "$out") bytes)"
    rm -f "$out"
}

# ── custom grid_beats=0.5 accepted ───────────────────────────────────────────

test_quantize_eighth_grid() {
    local mid out code
    mid=$(mktemp --suffix=.mid)
    _build_midi "$mid" || { rm -f "$mid"; return 1; }
    out=$(mktemp)
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.mid"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"grid_beats\":0.5,\"output_path\":\"$_out\"}" \
        -o /dev/null \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/quantize")
    rm -f "$mid"
    assert_eq "$code" "200" "grid_beats=0.5 -> 200" || { rm -f "$out"; return 1; }
    curl -sf -o "$out" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: fetch staged quantized failed"; rm -f "$out"; return 1
    }
    if [ "$(head -c 4 "$out")" != "MThd" ]; then
        echo "  FAIL: not MIDI"; rm -f "$out"; return 1
    fi
    echo "OK: quantize_eighth_grid"
    rm -f "$out"
}

# ── grid_beats <= 0 → 400 ────────────────────────────────────────────────────

test_quantize_zero_grid_400() {
    local mid code
    mid=$(mktemp --suffix=.mid)
    _build_midi "$mid" || { rm -f "$mid"; return 1; }
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"grid_beats\":0,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/quantize")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    rm -f "$mid"
    assert_eq "$code" "400" "grid_beats=0 -> 400" || return 1
    echo "OK: quantize_zero_grid_400"
}

# ── non-MIDI input → 400 ─────────────────────────────────────────────────────

test_quantize_non_midi_400() {
    local bogus code
    bogus=$(mktemp)
    echo "not a midi file" > "$bogus"
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${bogus}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${bogus}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/quantize")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    rm -f "$bogus"
    assert_eq "$code" "400" "non-MIDI input -> 400" || return 1
    echo "OK: quantize_non_midi_400"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_quantize_output_path() {
    local mid body code fetched
    mid=$(mktemp --suffix=.mid)
    _build_midi "$mid" || { rm -f "$mid"; return 1; }
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${mid}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${mid}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"midi/quantized.mid\"}" \
        "${AUDIOLLA_BASE_URL}/v1/midi/quantize")
    rm -f "$mid"
    if ! echo "$body" | jq -e '.path == "midi/quantized.mid"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/midi/quantized.mid")
    assert_eq "$code" "200" "GET staged quantize -> 200" || { rm -f "$fetched"; return 1; }
    if [ "$(head -c 4 "$fetched")" != "MThd" ]; then
        echo "  FAIL: staged file is not MIDI (no MThd)"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: quantize_output_path"
}

harness_run_tests \
    test_quantize_returns_midi \
    test_quantize_eighth_grid \
    test_quantize_zero_grid_400 \
    test_quantize_non_midi_400 \
    test_quantize_output_path
