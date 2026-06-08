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
    local code body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(mktemp)
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"effects\":[{\"type\":\"Gain\",\"params\":{\"gain_db\":-3.0}}],\"output_format\":\"wav\",\"output_path\":\"$_out\"}" \
        -o "$body" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    assert_eq "$code" "200" "fx Gain -> 200" || { rm -f "$body"; return 1; }
    jq -e '.path == "'"$_out"'"' "$body" >/dev/null || {
        echo "  FAIL: response missing path; got: $(cat "$body")"; rm -f "$body"; return 1
    }
    rm -f "$body"
    # Verify the staged output is fetchable WAV
    local fetched
    fetched=$(mktemp)
    curl -sf -o "$fetched" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: could not fetch staged output"; rm -f "$fetched"; return 1
    }
    if [ "$(stat -c%s "$fetched")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: fx_single_gain"
}

# ── chain of multiple effects → audio back ───────────────────────────────────

test_fx_compressor_reverb_chain() {
    local code body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/chain-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(mktemp)
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"effects\":[{\"type\":\"Compressor\",\"params\":{\"threshold_db\":-18,\"ratio\":4.0}},{\"type\":\"Reverb\",\"params\":{\"room_size\":0.5,\"wet_level\":0.3}},{\"type\":\"Gain\",\"params\":{\"gain_db\":-3.0}}],\"output_format\":\"wav\",\"output_path\":\"$_out\"}" \
        -o "$body" \
        -w "%{http_code}" \
        --max-time 60 \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    assert_eq "$code" "200" "fx chain -> 200" || { rm -f "$body"; return 1; }
    [ -s "$body" ] || { echo "  FAIL: empty response"; rm -f "$body"; return 1; }
    rm -f "$body"
    echo "OK: fx_compressor_reverb_chain"
}

# ── pitch shift produces a valid audio file ──────────────────────────────────

test_fx_pitch_shift() {
    local code body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/ps-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(mktemp)
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"effects\":[{\"type\":\"PitchShift\",\"params\":{\"semitones\":3.0}}],\"output_format\":\"wav\",\"output_path\":\"$_out\"}" \
        -o "$body" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    assert_eq "$code" "200" "fx PitchShift -> 200" || { rm -f "$body"; return 1; }
    [ -s "$body" ] || { echo "  FAIL: empty response"; rm -f "$body"; return 1; }
    rm -f "$body"
    echo "OK: fx_pitch_shift"
}

# ── output_path round-trip ───────────────────────────────────────────────────

test_fx_output_path_roundtrip() {
    local code body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"effects\":[{\"type\":\"Gain\",\"params\":{\"gain_db\":0.0}}],\"output_format\":\"wav\",\"output_path\":\"fx/out.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    if ! echo "$body" | jq -e '.path == "fx/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; got: $body"; return 1
    fi

    # The written file is retrievable.
    local fetched code
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/fx/out.wav")
    assert_eq "$code" "200" "GET fx output -> 200" || { rm -f "$fetched"; return 1; }
    [ -s "$fetched" ] || { echo "  FAIL: staged file is not a WAV"; rm -f "$fetched"; return 1; }
    rm -f "$fetched"
    echo "OK: fx_output_path_roundtrip"
}

# ── validation: missing required `effects` field → 422 (Pydantic) ────────────

test_fx_bad_json_400() {
    local code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    assert_eq "$code" "422" "fx missing effects -> 422" || return 1
    echo "OK: fx_bad_json_400"
}

# ── validation: unknown effect type → 400 (handler-level allowlist) ──────────

test_fx_unknown_type_400() {
    local code body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(mktemp)
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"effects\":[{\"type\":\"NoSuchEffect\",\"params\":{}}],\"output_path\":\"$_out\"}" \
        -o "$body" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    assert_eq "$code" "400" "fx unknown type -> 400" || { rm -f "$body"; return 1; }
    grep -qi "not allowed" "$body" || {
        echo "  FAIL: detail missing 'not allowed'; got: $(cat "$body")"; rm -f "$body"; return 1
    }
    rm -f "$body"
    echo "OK: fx_unknown_type_400"
}

# ── validation: VST plugin classes are NOT in the allowlist ──────────────────

test_fx_vst_blocked_400() {
    local code body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(mktemp)
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"effects\":[{\"type\":\"VST3Plugin\",\"params\":{}}],\"output_path\":\"$_out\"}" \
        -o "$body" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/fx")
    assert_eq "$code" "400" "fx VST blocked -> 400" || { rm -f "$body"; return 1; }
    rm -f "$body"
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
