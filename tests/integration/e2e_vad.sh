#!/bin/bash
# Voice activity detection — /v1/audio/vad.
#
#     bash tests/integration/e2e_vad.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "silero-vad"

# ── basic: returns speech_segments + speech_ratio ────────────────────────────

test_vad_returns_speech_segments() {
    local body
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/vad")
    if ! echo "$body" | jq -e '.speech_segments | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: speech_segments not an array; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.speech_ratio | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: speech_ratio missing or not a number; body: $body"; return 1
    fi
    echo "OK: vad_returns_speech_segments (ratio=$(echo "$body" | jq -r '.speech_ratio'))"
}

# ── missing file → 4xx ───────────────────────────────────────────────────────

test_vad_rejects_missing_file() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        "${AUDIOLLA_BASE_URL}/v1/audio/vad")
    if [ "$code" -lt 400 ] || [ "$code" -ge 500 ]; then
        echo "  FAIL: expected 4xx, got $code"; return 1
    fi
    echo "OK: vad_rejects_missing_file (HTTP $code)"
}

# ── custom threshold ─────────────────────────────────────────────────────────

test_vad_custom_threshold() {
    local body
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "threshold=0.7" \
        "${AUDIOLLA_BASE_URL}/v1/audio/vad")
    if ! echo "$body" | jq -e '.speech_segments | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: speech_segments missing with custom threshold; body: $body"; return 1
    fi
    # Response echoes back the threshold that was used.
    if ! echo "$body" | jq -e '.threshold == 0.7' >/dev/null 2>&1; then
        echo "  FAIL: response threshold not 0.7; body: $body"; return 1
    fi
    echo "OK: vad_custom_threshold"
}

# ── min_speech_duration_ms filters short speech bursts ───────────────────────

test_vad_min_speech_duration_ms() {
    local body
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "min_speech_duration_ms=500" \
        "${AUDIOLLA_BASE_URL}/v1/audio/vad")
    if ! echo "$body" | jq -e '.speech_segments | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: speech_segments missing; body: $body"; return 1
    fi
    # Every returned speech segment must be at least 500ms long.
    local short_count
    short_count=$(echo "$body" | jq -r '[.speech_segments[] | select((.end_sec - .start_sec) < 0.499)] | length')
    if [ "${short_count:-0}" -gt 0 ]; then
        echo "  FAIL: $short_count segment(s) shorter than min_speech_duration_ms=500; body: $body"
        return 1
    fi
    echo "OK: vad_min_speech_duration_ms"
}

# ── min_silence_duration_ms merges gaps shorter than threshold ───────────────

test_vad_min_silence_duration_ms() {
    local body
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "min_silence_duration_ms=500" \
        "${AUDIOLLA_BASE_URL}/v1/audio/vad")
    if ! echo "$body" | jq -e '.speech_segments | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: speech_segments missing; body: $body"; return 1
    fi
    echo "OK: vad_min_silence_duration_ms"
}

harness_run_tests \
    test_vad_returns_speech_segments \
    test_vad_rejects_missing_file \
    test_vad_custom_threshold \
    test_vad_min_speech_duration_ms \
    test_vad_min_silence_duration_ms
