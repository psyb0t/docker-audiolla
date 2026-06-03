#!/bin/bash
# BPM match — /v1/audio/bpm-match end-to-end.
#
#     bash tests/integration/e2e_bpm_match.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze,stretch"

# Generate a click-track fixture: 8 s of 880 Hz clicks at 120 BPM (every 0.5 s).
# The plain sine-wave fixture has no perceivable beat; librosa needs rhythmic
# content to return a non-zero BPM.
BEAT_FIXTURE="${_DIR}/.fixtures/beat_click.wav"
docker run --rm \
    -u "$(id -u):$(id -g)" \
    -v "${_DIR}/.fixtures:${_DIR}/.fixtures" \
    --entrypoint ffmpeg "${HARNESS_IMAGE}" \
    -hide_banner -loglevel error \
    -f lavfi \
    -i "aevalsrc=sin(2*PI*880*t)*if(lt(mod(t\,0.5)\,0.05)\,1\,0):s=44100:d=8" \
    -ar 44100 -y "$BEAT_FIXTURE" \
    || { echo "FATAL: beat fixture generation failed" >&2; exit 1; }
[ -s "$BEAT_FIXTURE" ] || { echo "FATAL: beat fixture is empty" >&2; exit 1; }

# ── returns WAV with required JSON fields ─────────────────────────────────────

test_bpm_match_returns_wav() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 180 \
        -X POST \
        -F "file=@${BEAT_FIXTURE}" \
        -F "target_bpm=120.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/bpm-match")
    assert_eq "$code" "200" "bpm-match -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: bpm_match_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── output_path returns JSON with source/target BPM metadata ─────────────────

test_bpm_match_json_metadata() {
    local body src_bpm target_bpm
    body=$(curl -s --max-time 180 -X POST \
        -F "file=@${BEAT_FIXTURE}" \
        -F "target_bpm=140.0" \
        -F "output_path=bpm/matched.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/bpm-match")
    src_bpm=$(echo "$body" | jq -r '.source_bpm // empty')
    target_bpm=$(echo "$body" | jq -r '.target_bpm // empty')
    if [ -z "$src_bpm" ] || [ -z "$target_bpm" ]; then
        echo "  FAIL: missing BPM metadata; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.target_bpm == 140.0' >/dev/null 2>&1; then
        echo "  FAIL: target_bpm mismatch; body: $body"; return 1
    fi
    echo "OK: bpm_match_json_metadata (source=${src_bpm} target=${target_bpm})"
}

# ── pitch_semitones preserved in output ───────────────────────────────────────

test_bpm_match_with_pitch() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 180 \
        -X POST \
        -F "file=@${BEAT_FIXTURE}" \
        -F "target_bpm=100.0" \
        -F "pitch_semitones=2.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/bpm-match")
    assert_eq "$code" "200" "bpm-match with pitch -> 200" || return 1
    echo "OK: bpm_match_with_pitch"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_bpm_match_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 180 \
        -X POST \
        -F "file=@${BEAT_FIXTURE}" \
        -F "target_bpm=120.0" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/bpm-match")
    assert_eq "$code" "200" "bpm-match mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: bpm_match_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── target_bpm <= 0 → 400 ────────────────────────────────────────────────────

test_bpm_match_zero_target_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_bpm=0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/bpm-match")
    assert_eq "$code" "400" "target_bpm=0 -> 400" || return 1
    echo "OK: bpm_match_zero_target_400"
}

# ── target_bpm missing → 422 ─────────────────────────────────────────────────

test_bpm_match_missing_target_422() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/bpm-match")
    assert_eq "$code" "422" "missing target_bpm -> 422" || return 1
    echo "OK: bpm_match_missing_target_422"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_bpm_match_missing_file_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        -F "target_bpm=120.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/bpm-match")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: bpm_match_missing_file_404"
}

harness_run_tests \
    test_bpm_match_returns_wav \
    test_bpm_match_json_metadata \
    test_bpm_match_with_pitch \
    test_bpm_match_output_format_mp3 \
    test_bpm_match_zero_target_400 \
    test_bpm_match_missing_target_422 \
    test_bpm_match_missing_file_404
