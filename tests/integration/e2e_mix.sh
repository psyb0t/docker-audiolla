#!/bin/bash
# Multi-track mix — /v1/audio/mix end-to-end.
#
#     bash tests/integration/e2e_mix.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

# The mix endpoint takes staged paths. Stage the fixture first via output_path,
# then reference it. We stage two copies: track_a.wav and track_b.wav.
_stage_fixtures() {
    curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "start_sec=0.0" \
        -F "end_sec=4.0" \
        -F "output_path=mix/track_a.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim" > /dev/null || return 1
    curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "start_sec=0.0" \
        -F "end_sec=4.0" \
        -F "output_path=mix/track_b.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim" > /dev/null || return 1
}

harness_start "librosa-analyze"
_stage_fixtures || { echo "FATAL: fixture staging failed" >&2; exit 1; }

TRACKS_JSON='[{"file_path":"mix/track_a.wav","gain_db":0},{"file_path":"mix/track_b.wav","gain_db":0}]'
TRACKS_GAIN='[{"file_path":"mix/track_a.wav","gain_db":-6},{"file_path":"mix/track_b.wav","gain_db":-3}]'

# ── two tracks → 200 WAV ──────────────────────────────────────────────────────

test_mix_returns_wav() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "tracks=${TRACKS_JSON}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mix")
    assert_eq "$code" "200" "mix -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: mix_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── per-track gain_db accepted ────────────────────────────────────────────────

test_mix_with_gain() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "tracks=${TRACKS_GAIN}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mix")
    assert_eq "$code" "200" "mix with gain_db -> 200" || return 1
    echo "OK: mix_with_gain"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_mix_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "tracks=${TRACKS_JSON}" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mix")
    assert_eq "$code" "200" "mix mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: mix_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── only one track → 400 ─────────────────────────────────────────────────────

test_mix_one_track_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F 'tracks=[{"file_path":"mix/track_a.wav"}]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/mix")
    assert_eq "$code" "400" "one track -> 400" || return 1
    echo "OK: mix_one_track_400"
}

# ── invalid JSON tracks → 400 ────────────────────────────────────────────────

test_mix_invalid_tracks_json_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "tracks=not-json" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mix")
    assert_eq "$code" "400" "invalid JSON -> 400" || return 1
    echo "OK: mix_invalid_tracks_json_400"
}

# ── tracks missing → 422 (required) ─────────────────────────────────────────

test_mix_missing_tracks_422() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        "${AUDIOLLA_BASE_URL}/v1/audio/mix")
    assert_eq "$code" "422" "missing tracks -> 422" || return 1
    echo "OK: mix_missing_tracks_422"
}

# ── track file not found → 404 (status propagates from input_resolver) ──────

test_mix_missing_track_file_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F 'tracks=[{"file_path":"mix/track_a.wav"},{"file_path":"mix/ghost.wav"}]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/mix")
    assert_eq "$code" "404" "missing track file -> 404" || return 1
    echo "OK: mix_missing_track_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_mix_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "tracks=${TRACKS_JSON}" \
        -F "output_path=mix/mixed.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/mix")
    if ! echo "$body" | jq -e '.path == "mix/mixed.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/mix/mixed.wav")
    assert_eq "$code" "200" "GET staged mix -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: mix_output_path"
}

harness_run_tests \
    test_mix_returns_wav \
    test_mix_with_gain \
    test_mix_output_format_mp3 \
    test_mix_one_track_400 \
    test_mix_invalid_tracks_json_400 \
    test_mix_missing_tracks_422 \
    test_mix_missing_track_file_404 \
    test_mix_output_path
