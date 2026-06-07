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

# ── 3-band split returns valid WAV ───────────────────────────────────────────

test_multiband_3band_returns_wav() {
    local tmpf code in_sz out_sz
    tmpf=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 90 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'crossovers_hz=[200, 3000]' \
        -F 'bands=[{"threshold_db":-18,"ratio":4},{"threshold_db":-14,"ratio":3},{"threshold_db":-10,"ratio":2}]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "200" "multiband 3-band -> 200" || { rm -f "$tmpf"; return 1; }
    if ! head -c 4 "$tmpf" | grep -q "RIFF"; then
        echo "  FAIL: output is not WAV"; rm -f "$tmpf"; return 1
    fi
    in_sz=$(stat -c%s "$FIXTURE")
    out_sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    # Output should be similar size — same sample rate, same duration, float→PCM via ffmpeg
    if [ "$out_sz" -lt $((in_sz / 4)) ] || [ "$out_sz" -gt $((in_sz * 4)) ]; then
        echo "  FAIL: output size ($out_sz) wildly different from input ($in_sz)"; return 1
    fi
    echo "OK: multiband_3band_returns_wav (in=$in_sz out=$out_sz)"
}

# ── 4-band split with optional per-band params ───────────────────────────────

test_multiband_4band_full_params() {
    local tmpf code
    tmpf=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 90 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'crossovers_hz=[150, 800, 4000]' \
        -F 'bands=[
            {"threshold_db":-20,"ratio":5,"attack_ms":20,"release_ms":200,"makeup_db":2.0},
            {"threshold_db":-16,"ratio":4,"attack_ms":12,"release_ms":120,"makeup_db":1.5},
            {"threshold_db":-12,"ratio":3,"attack_ms":6, "release_ms":60, "makeup_db":1.0},
            {"threshold_db":-8, "ratio":2,"attack_ms":2, "release_ms":30, "makeup_db":0.5}
        ]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "200" "multiband 4-band full params -> 200" || { rm -f "$tmpf"; return 1; }
    head -c 4 "$tmpf" | grep -q "RIFF" || { echo "  FAIL: not WAV"; rm -f "$tmpf"; return 1; }
    rm -f "$tmpf"
    echo "OK: multiband_4band_full_params"
}

# ── output_path stages WAV ───────────────────────────────────────────────────

test_multiband_output_path() {
    local body code fetched
    body=$(curl -s --max-time 90 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'crossovers_hz=[500]' \
        -F 'bands=[{"threshold_db":-15,"ratio":3},{"threshold_db":-12,"ratio":2}]' \
        -F "output_path=mbc_test/out.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    if ! echo "$body" | jq -e '.path == "mbc_test/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.crossovers_hz | length == 1' >/dev/null 2>&1; then
        echo "  FAIL: crossovers_hz missing from extra_json; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/mbc_test/out.wav")
    assert_eq "$code" "200" "GET staged WAV -> 200" || { rm -f "$fetched"; return 1; }
    head -c 4 "$fetched" | grep -q "RIFF" || {
        echo "  FAIL: staged file not WAV"; rm -f "$fetched"; return 1
    }
    rm -f "$fetched"
    echo "OK: multiband_output_path"
}

# ── output_format=mp3 ────────────────────────────────────────────────────────

test_multiband_output_format_mp3() {
    local tmpf code
    tmpf=$(mktemp --suffix=.mp3)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 90 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'crossovers_hz=[1000]' \
        -F 'bands=[{"threshold_db":-15,"ratio":3},{"threshold_db":-12,"ratio":2}]' \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "200" "multiband mp3 -> 200" || { rm -f "$tmpf"; return 1; }
    if [ ! -s "$tmpf" ]; then echo "  FAIL: empty mp3"; rm -f "$tmpf"; return 1; fi
    rm -f "$tmpf"
    echo "OK: multiband_output_format_mp3"
}

# ── bands length != crossovers+1 → 400 ───────────────────────────────────────

test_multiband_bad_bands_length_400() {
    local code body
    body=$(curl -s -w "\n%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'crossovers_hz=[200, 2000]' \
        -F 'bands=[{"threshold_db":-15,"ratio":3}]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    code=$(echo "$body" | tail -n1)
    assert_eq "$code" "400" "wrong bands length -> 400" || return 1
    echo "OK: multiband_bad_bands_length_400"
}

# ── empty crossovers → 400 ───────────────────────────────────────────────────

test_multiband_empty_crossovers_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'crossovers_hz=[]' \
        -F 'bands=[]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "400" "empty crossovers -> 400" || return 1
    echo "OK: multiband_empty_crossovers_400"
}

# ── malformed JSON → 400 ─────────────────────────────────────────────────────

test_multiband_bad_json_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'crossovers_hz=not-json' \
        -F 'bands=[]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/multiband-compress")
    assert_eq "$code" "400" "bad JSON -> 400" || return 1
    echo "OK: multiband_bad_json_400"
}

# ── crossover >= nyquist → 400 ───────────────────────────────────────────────

test_multiband_crossover_above_nyquist_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'crossovers_hz=[99000]' \
        -F 'bands=[{"threshold_db":-15,"ratio":3},{"threshold_db":-12,"ratio":2}]' \
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
