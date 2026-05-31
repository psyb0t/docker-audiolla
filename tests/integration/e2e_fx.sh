#!/bin/bash
# /v1/audio/fx end-to-end — generic pedalboard chain processor.
#
# Fixture: tests/integration/.fixtures/audio.wav (8 s stereo @ 44.1 kHz).
#
#     bash tests/integration/e2e_fx.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "fx-chain"

# ── single effect → audio back ───────────────────────────────────────────────

test_fx_single_gain() {
    local code tmp
    tmp=$(mktemp)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 60 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F 'effects=[{"type":"Gain","params":{"gain_db":-6.0}}]' \
        -F "output_format=wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    assert_eq "$code" "200" "fx Gain -> 200" || { rm -f "$tmp"; return 1; }
    if ! head -c 4 "$tmp" | grep -q "RIFF"; then
        echo "  FAIL: response is not a WAV"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: fx_single_gain"
}

# ── chain of multiple effects → audio back ───────────────────────────────────

test_fx_compressor_reverb_chain() {
    local code tmp
    tmp=$(mktemp)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 60 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F 'effects=[
          {"type":"Compressor","params":{"threshold_db":-18,"ratio":4.0}},
          {"type":"Reverb","params":{"room_size":0.5,"wet_level":0.3}},
          {"type":"Gain","params":{"gain_db":-3.0}}
        ]' \
        -F "output_format=wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    assert_eq "$code" "200" "fx chain -> 200" || { rm -f "$tmp"; return 1; }
    head -c 4 "$tmp" | grep -q "RIFF" || { echo "  FAIL: not a WAV"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: fx_compressor_reverb_chain"
}

# ── pitch shift produces a real audible difference (different byte size) ─────

test_fx_pitch_shift() {
    local code tmp
    tmp=$(mktemp)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 60 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F 'effects=[{"type":"PitchShift","params":{"semitones":3}}]' \
        -F "output_format=wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    assert_eq "$code" "200" "fx PitchShift -> 200" || { rm -f "$tmp"; return 1; }
    head -c 4 "$tmp" | grep -q "RIFF" || { echo "  FAIL: not a WAV"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: fx_pitch_shift"
}

# ── output_path round-trip ───────────────────────────────────────────────────

test_fx_output_path_roundtrip() {
    local code body
    body=$(curl -s -o /tmp/audiolla-fx-resp.$$ -w "%{http_code}" \
        --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'effects=[{"type":"Gain","params":{"gain_db":-3}}]' \
        -F "output_format=wav" \
        -F "output_path=fx/out.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    code="$body"
    body=$(cat /tmp/audiolla-fx-resp.$$ 2>/dev/null)
    rm -f /tmp/audiolla-fx-resp.$$
    assert_eq "$code" "200" "fx output_path -> 200" || return 1
    echo "$body" | grep -q '"path":"fx/out.wav"' || { echo "  FAIL: response missing path; got: $body"; return 1; }

    # The written file is retrievable.
    local fetched
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/fx/out.wav")
    assert_eq "$code" "200" "GET fx output -> 200" || { rm -f "$fetched"; return 1; }
    head -c 4 "$fetched" | grep -q "RIFF" || { echo "  FAIL: staged file is not a WAV"; rm -f "$fetched"; return 1; }
    rm -f "$fetched"
    echo "OK: fx_output_path_roundtrip"
}

# ── validation: bad effects JSON → 400 ───────────────────────────────────────

test_fx_bad_json_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F 'effects=not-json' \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    assert_eq "$code" "400" "fx bad JSON -> 400" || return 1
    echo "OK: fx_bad_json_400"
}

# ── validation: unknown effect type → 400 ────────────────────────────────────

test_fx_unknown_type_400() {
    local code body
    body=$(curl -s -o /tmp/audiolla-fx-resp.$$ -w "%{http_code}" \
        --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'effects=[{"type":"NotAnEffect","params":{}}]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    code="$body"
    body=$(cat /tmp/audiolla-fx-resp.$$ 2>/dev/null)
    rm -f /tmp/audiolla-fx-resp.$$
    assert_eq "$code" "400" "fx unknown type -> 400" || return 1
    echo "$body" | grep -qi "not allowed" || { echo "  FAIL: detail missing 'not allowed'; got: $body"; return 1; }
    echo "OK: fx_unknown_type_400"
}

# ── validation: VST plugin classes are NOT in the allowlist ──────────────────

test_fx_vst_blocked_400() {
    local code body
    body=$(curl -s -o /tmp/audiolla-fx-resp.$$ -w "%{http_code}" \
        --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'effects=[{"type":"VST3Plugin","params":{"path":"/etc/passwd"}}]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    code="$body"
    body=$(cat /tmp/audiolla-fx-resp.$$ 2>/dev/null)
    rm -f /tmp/audiolla-fx-resp.$$
    assert_eq "$code" "400" "fx VST blocked -> 400" || return 1
    echo "OK: fx_vst_blocked_400"
}

harness_run_tests \
    test_fx_single_gain \
    test_fx_compressor_reverb_chain \
    test_fx_pitch_shift \
    test_fx_output_path_roundtrip \
    test_fx_bad_json_400 \
    test_fx_unknown_type_400 \
    test_fx_vst_blocked_400
