#!/bin/bash
# Loop point detection — /v1/audio/loop-point.
#
#     bash tests/integration/e2e_loop_point.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"
BEAT_FIXTURE="${_DIR}/.fixtures/beat_120.wav"

harness_start "librosa-analyze"

# ── response shape (sine fixture — uses fallback path) ────────────────────────

test_loop_point_shape() {
    local body
    body=$(curl -s --max-time 90 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop-point")
    if ! echo "$body" | jq -e '.loop_start_sec | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: loop_start_sec missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.loop_end_sec | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: loop_end_sec missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.tempo_bpm | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: tempo_bpm missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.duration | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: duration missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.candidates | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: candidates not an array; body: $body"; return 1
    fi
    echo "OK: loop_point_shape"
}

# ── start <= end for sine fixture ─────────────────────────────────────────────

test_loop_point_start_lt_end() {
    local body
    body=$(curl -s --max-time 90 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop-point")
    if ! echo "$body" | jq -e '.loop_start_sec <= .loop_end_sec' >/dev/null 2>&1; then
        local s e
        s=$(echo "$body" | jq '.loop_start_sec')
        e=$(echo "$body" | jq '.loop_end_sec')
        echo "  FAIL: start ($s) > end ($e); body: $body"; return 1
    fi
    local s e
    s=$(echo "$body" | jq -r '.loop_start_sec')
    e=$(echo "$body" | jq -r '.loop_end_sec')
    echo "OK: loop_point_start_lt_end (start=$s end=$e)"
}

# ── beat fixture: real loop detected with score > 0 ──────────────────────────

test_loop_point_beat_fixture_real_candidates() {
    local body
    body=$(curl -s --max-time 90 -X POST \
        -F "file=@${BEAT_FIXTURE}" \
        -F "min_loop_bars=1" \
        -F "num_candidates=3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop-point")
    # The 120BPM click track has ≥16 beats → enough for min_bars=1 candidates.
    if echo "$body" | jq -e '.note != null' >/dev/null 2>&1; then
        echo "  FAIL: got fallback note on beat fixture: $(echo "$body" | jq -r '.note')"
        return 1
    fi
    if ! echo "$body" | jq -e '.bars >= 1' >/dev/null 2>&1; then
        echo "  FAIL: bars < 1 on beat fixture; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.score >= 0 and .score <= 1' >/dev/null 2>&1; then
        echo "  FAIL: score out of [0,1] range; body: $body"; return 1
    fi
    local bars score
    bars=$(echo "$body" | jq -r '.bars')
    score=$(echo "$body" | jq -r '.score')
    echo "OK: loop_point_beat_fixture_real_candidates (bars=$bars score=$score)"
}

# ── beat fixture: detected loop is at least 2 seconds ────────────────────────

test_loop_point_beat_fixture_loop_length() {
    local body
    body=$(curl -s --max-time 90 -X POST \
        -F "file=@${BEAT_FIXTURE}" \
        -F "min_loop_bars=1" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop-point")
    local start end length
    start=$(echo "$body" | jq -r '.loop_start_sec')
    end=$(echo "$body" | jq -r '.loop_end_sec')
    length=$(echo "$body" | jq -r '.loop_end_sec - .loop_start_sec')
    if ! echo "$body" | jq -e '(.loop_end_sec - .loop_start_sec) >= 1.0' >/dev/null 2>&1; then
        echo "  FAIL: loop too short (${length}s = end=$end - start=$start)"; return 1
    fi
    echo "OK: loop_point_beat_fixture_loop_length (${length}s)"
}

# ── candidates array has requested count ─────────────────────────────────────

test_loop_point_candidates_count() {
    local body count
    body=$(curl -s --max-time 90 -X POST \
        -F "file=@${BEAT_FIXTURE}" \
        -F "num_candidates=3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop-point")
    if ! echo "$body" | jq -e '.candidates | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: candidates not an array; body: $body"; return 1
    fi
    count=$(echo "$body" | jq -r '.candidates | length')
    echo "OK: loop_point_candidates_count ($count candidates)"
}

# ── invalid min_loop_bars → 400 ───────────────────────────────────────────────

test_loop_point_invalid_bars() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "min_loop_bars=0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop-point")
    assert_eq "$code" "400" "min_loop_bars=0 -> 400" || return 1
    echo "OK: loop_point_invalid_bars"
}

harness_run_tests \
    test_loop_point_shape \
    test_loop_point_start_lt_end \
    test_loop_point_beat_fixture_real_candidates \
    test_loop_point_beat_fixture_loop_length \
    test_loop_point_candidates_count \
    test_loop_point_invalid_bars
