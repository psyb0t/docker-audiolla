#!/bin/bash
# Silence detection — /v1/audio/silence end-to-end.
#
#     bash tests/integration/e2e_silence.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"
FIXTURE_DIR="${_DIR}/.fixtures"
SILENT_FIXTURE="${FIXTURE_DIR}/silence-padded.wav"

harness_start "silence-detect"

# Build a fixture with a known-silent gap so we can test both detect +
# trim. ffmpeg in the prod image; we synthesise via lavfi `anullsrc`
# between two short sine segments.
build_silence_fixture() {
    if [ -f "$SILENT_FIXTURE" ]; then
        return 0
    fi
    docker run --rm \
        --entrypoint ffmpeg \
        -v "${FIXTURE_DIR}:${FIXTURE_DIR}" \
        "$HARNESS_IMAGE" \
        -y -hide_banner -nostats \
        -f lavfi -i "sine=frequency=440:duration=2,volume=0.5" \
        -f lavfi -i "anullsrc=duration=3" \
        -f lavfi -i "sine=frequency=880:duration=2,volume=0.5" \
        -filter_complex "[0:a][1:a][2:a]concat=n=3:v=0:a=1[outa]" \
        -map "[outa]" -ac 1 -ar 44100 \
        "$SILENT_FIXTURE" >/dev/null 2>&1
    if [ ! -f "$SILENT_FIXTURE" ]; then
        echo "  FAIL: could not build silence fixture"
        return 1
    fi
}

# ── detect: finds the 3-second silent gap in the middle ─────────────────────

test_silence_detect_finds_gap() {
    build_silence_fixture || return 1
    local body silent_count
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${SILENT_FIXTURE}" \
        -F "threshold_db=-30" \
        -F "min_duration_sec=1.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/silence")
    if ! echo "$body" | jq -e '.silent_ranges | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: silent_ranges missing; body: $body"; return 1
    fi
    silent_count=$(echo "$body" | jq -r '.silent_ranges | length')
    if [ "$silent_count" -lt 1 ]; then
        echo "  FAIL: didn't detect the 3-second silent gap; body: $body"
        return 1
    fi
    # The detected gap should be ~3 seconds long.
    if ! echo "$body" | jq -e '.silent_ranges[0].duration_sec > 2.5 and .silent_ranges[0].duration_sec < 3.5' >/dev/null 2>&1; then
        echo "  FAIL: detected gap not ~3s; body: $body"
        return 1
    fi
    if ! echo "$body" | jq -e '.non_silent_ranges | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: non_silent_ranges missing; body: $body"; return 1
    fi
    echo "OK: silence_detect_finds_gap"
}

# ── trim=all: removes the silent gap, output is shorter than input ──────────

test_silence_trim_all_returns_shorter_audio() {
    build_silence_fixture || return 1
    local body b64 decoded
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${SILENT_FIXTURE}" \
        -F "threshold_db=-30" \
        -F "min_duration_sec=1.0" \
        -F "trim_mode=all" \
        "${AUDIOLLA_BASE_URL}/v1/audio/silence")
    b64=$(echo "$body" | jq -r '.trimmed_audio_base64 // empty')
    if [ -z "$b64" ]; then
        echo "  FAIL: trimmed_audio_base64 missing; body: $(echo "$body" | head -c 500)"; return 1
    fi
    decoded=$(mktemp)
    echo "$b64" | base64 -d > "$decoded"
    if ! head -c 4 "$decoded" | grep -q "RIFF"; then
        echo "  FAIL: trimmed output is not WAV"
        rm -f "$decoded"; return 1
    fi
    # ffprobe-ish: input is 7s (~~700kB raw at 44.1kHz mono 16-bit);
    # trimmed should be ~4s (~~350kB). Loose check on byte size.
    local insize outsize
    insize=$(stat -c%s "$SILENT_FIXTURE")
    outsize=$(stat -c%s "$decoded")
    rm -f "$decoded"
    if [ "$outsize" -ge "$insize" ]; then
        echo "  FAIL: trimmed output ($outsize) not smaller than input ($insize)"
        return 1
    fi
    echo "OK: silence_trim_all_returns_shorter_audio (in=$insize out=$outsize)"
}

# ── trim=edges + output_path: writes trimmed to staging ─────────────────────

test_silence_trim_edges_output_path() {
    build_silence_fixture || return 1
    local body code fetched
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${SILENT_FIXTURE}" \
        -F "threshold_db=-30" \
        -F "min_duration_sec=1.0" \
        -F "trim_mode=edges" \
        -F "output_path=silence/trimmed.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/silence")
    if ! echo "$body" | jq -e '.path == "silence/trimmed.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/silence/trimmed.wav")
    assert_eq "$code" "200" "GET trimmed -> 200" || { rm -f "$fetched"; return 1; }
    head -c 4 "$fetched" | grep -q "RIFF" || { echo "  FAIL: staged not WAV"; rm -f "$fetched"; return 1; }
    rm -f "$fetched"
    echo "OK: silence_trim_edges_output_path"
}

# ── invalid threshold (positive dBFS) → 400 ─────────────────────────────────

test_silence_bad_threshold_400() {
    build_silence_fixture || return 1
    local code body
    body=$(curl -s -o /tmp/audiolla-silence.$$ -w "%{http_code}" \
        --max-time 30 -X POST \
        -F "file=@${SILENT_FIXTURE}" \
        -F "threshold_db=5" \
        "${AUDIOLLA_BASE_URL}/v1/audio/silence")
    code="$body"
    body=$(cat /tmp/audiolla-silence.$$ 2>/dev/null)
    rm -f /tmp/audiolla-silence.$$
    assert_eq "$code" "400" "threshold > 0 -> 400" || return 1
    if ! echo "$body" | grep -qi "threshold"; then
        echo "  FAIL: detail missing threshold; body: $body"; return 1
    fi
    echo "OK: silence_bad_threshold_400"
}

harness_run_tests \
    test_silence_detect_finds_gap \
    test_silence_trim_all_returns_shorter_audio \
    test_silence_trim_edges_output_path \
    test_silence_bad_threshold_400
