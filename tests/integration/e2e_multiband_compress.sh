#!/bin/bash
# Multiband compression — /v1/audio/multiband-compress.
#
#     bash tests/integration/e2e_multiband_compress.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

# multiband-compress is a pure-DSP endpoint (pedalboard + scipy). The
# harness requires an engine slug for boot; librosa-analyze is the
# cheapest one.
harness_start "librosa-analyze"

# v1.0.0: crossovers_hz is a JSON array of numbers; bands is a JSON
# array of per-band compressor specs.
THREE_BANDS_CROSSOVERS='[200, 2000]'
THREE_BANDS_SPEC='[{"threshold_db":-18,"ratio":4,"attack_ms":10,"release_ms":100,"makeup_db":1.0},{"threshold_db":-12,"ratio":3,"attack_ms":8,"release_ms":80,"makeup_db":0.5},{"threshold_db":-6,"ratio":2,"attack_ms":4,"release_ms":40,"makeup_db":0.0}]'

ONE_CROSSOVER='[1000]'
TWO_BANDS_SPEC='[{"threshold_db":-18,"ratio":4},{"threshold_db":-12,"ratio":3}]'

FOUR_BANDS_CROSSOVERS='[150, 800, 4000]'
FOUR_BANDS_SPEC='[{"threshold_db":-20,"ratio":5,"attack_ms":20,"release_ms":200,"makeup_db":2.0},{"threshold_db":-16,"ratio":4,"attack_ms":12,"release_ms":120,"makeup_db":1.5},{"threshold_db":-12,"ratio":3,"attack_ms":6,"release_ms":60,"makeup_db":1.0},{"threshold_db":-8,"ratio":2,"attack_ms":2,"release_ms":30,"makeup_db":0.5}]'

# ── 3-band split returns valid WAV ───────────────────────────────────────────

test_multiband_3band_returns_wav() {
    local body code in_sz out_sz fetched
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="mbc-out/r3-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(mktemp)
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"crossovers_hz\":${THREE_BANDS_CROSSOVERS},\"bands\":${THREE_BANDS_SPEC},\"output_path\":\"$_out\"}" \
        -o "$body" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "200" "multiband 3-band -> 200" || { rm -f "$body"; return 1; }
    rm -f "$body"
    fetched=$(mktemp --suffix=.wav)
    curl -sf -o "$fetched" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: could not fetch staged output"; rm -f "$fetched"; return 1
    }
    if [ "$(stat -c%s "$fetched")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"; rm -f "$fetched"; return 1
    fi
    in_sz=$(stat -c%s "$FIXTURE")
    out_sz=$(stat -c%s "$fetched")
    rm -f "$fetched"
    # Output should be similar size — same sample rate, same duration
    if [ "$out_sz" -lt $((in_sz / 4)) ] || [ "$out_sz" -gt $((in_sz * 4)) ]; then
        echo "  FAIL: output size ($out_sz) wildly different from input ($in_sz)"; return 1
    fi
    echo "OK: multiband_3band_returns_wav (in=$in_sz out=$out_sz)"
}

# ── 4-band split with full per-band params ───────────────────────────────────

test_multiband_4band_full_params() {
    local code body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="mbc-out/r4-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(mktemp)
    code=$(curl -s -o "$body" -w "%{http_code}" --max-time 90 -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"crossovers_hz\":${FOUR_BANDS_CROSSOVERS},\"bands\":${FOUR_BANDS_SPEC},\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "200" "multiband 4-band full params -> 200" || { rm -f "$body"; return 1; }
    [ -s "$body" ] || { echo "  FAIL: empty response"; rm -f "$body"; return 1; }
    rm -f "$body"
    echo "OK: multiband_4band_full_params"
}

# ── output_path stages WAV; response carries crossovers_hz ───────────────────

test_multiband_output_path() {
    local body code fetched
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"crossovers_hz\":${ONE_CROSSOVER},\"bands\":${TWO_BANDS_SPEC},\"output_path\":\"mbc_test/out.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    if ! echo "$body" | jq -e '.path == "mbc_test/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.crossovers_hz | length == 1' >/dev/null 2>&1; then
        echo "  FAIL: crossovers_hz missing or wrong length in response; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/mbc_test/out.wav")
    assert_eq "$code" "200" "GET staged WAV -> 200" || { rm -f "$fetched"; return 1; }
    if ! head -c 4 "$fetched" | grep -q "RIFF"; then
        echo "  FAIL: staged file not WAV"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: multiband_output_path"
}

# ── output_format=mp3 ────────────────────────────────────────────────────────

test_multiband_output_format_mp3() {
    local code body fetched
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="mbc-out/mp3-$$-$RANDOM.mp3"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(mktemp)
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"crossovers_hz\":${ONE_CROSSOVER},\"bands\":${TWO_BANDS_SPEC},\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$body" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "200" "multiband mp3 -> 200" || { rm -f "$body"; return 1; }
    rm -f "$body"
    fetched=$(mktemp --suffix=.mp3)
    curl -sf -o "$fetched" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: could not fetch staged mp3"; rm -f "$fetched"; return 1
    }
    [ -s "$fetched" ] || { echo "  FAIL: empty mp3"; rm -f "$fetched"; return 1; }
    rm -f "$fetched"
    echo "OK: multiband_output_format_mp3"
}

# ── bands length != crossovers+1 → 400 (handler-level) ───────────────────────

test_multiband_bad_bands_length_400() {
    local code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="mbc-out/bad-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"crossovers_hz\":${THREE_BANDS_CROSSOVERS},\"bands\":[{\"threshold_db\":-18,\"ratio\":4}],\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "400" "wrong bands length -> 400" || return 1
    echo "OK: multiband_bad_bands_length_400"
}

# ── empty crossovers → 400 (handler-level) ───────────────────────────────────

test_multiband_empty_crossovers_400() {
    local code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="mbc-out/emp-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"crossovers_hz\":[],\"bands\":[{\"threshold_db\":-18,\"ratio\":4}],\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "400" "empty crossovers -> 400" || return 1
    echo "OK: multiband_empty_crossovers_400"
}

# ── missing required fields → 422 (Pydantic) ─────────────────────────────────

test_multiband_bad_json_400() {
    local code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="mbc-out/missing-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "422" "missing required fields -> 422" || return 1
    echo "OK: multiband_bad_json_400"
}

# ── crossover >= nyquist → 400 (handler-level) ───────────────────────────────

test_multiband_crossover_above_nyquist_400() {
    local code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="mbc-out/nyq-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"crossovers_hz\":[40000],\"bands\":[{\"threshold_db\":-18,\"ratio\":4},{\"threshold_db\":-12,\"ratio\":3}],\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "400" "crossover >= nyquist -> 400" || return 1
    echo "OK: multiband_crossover_above_nyquist_400"
}

harness_run_tests \
    test_multiband_3band_returns_wav \
    test_multiband_4band_full_params \
    test_multiband_output_path \
    test_multiband_output_format_mp3 \
    test_multiband_bad_bands_length_400 \
    test_multiband_empty_crossovers_400 \
    test_multiband_bad_json_400 \
    test_multiband_crossover_above_nyquist_400
