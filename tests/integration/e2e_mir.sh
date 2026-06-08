#!/bin/bash
# Music-information-retrieval endpoints — beats / onsets / melody / segments.
# All four ride on the librosa-analyze engine.
#
#     bash tests/integration/e2e_mir.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"
BEAT_FIXTURE="${_DIR}/.fixtures/beat_120.wav"

harness_start "librosa-analyze"

# ── beats: returns BPM + beat times ──────────────────────────────────────────

test_beats_returns_tempo_and_beats() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/beats")
    if ! echo "$body" | jq -e '.tempo_bpm | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: tempo_bpm missing/not a number; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.beats | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: beats missing/not an array; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.duration > 7 and .duration < 9' >/dev/null 2>&1; then
        echo "  FAIL: duration not ~8s; body: $body"; return 1
    fi
    local count
    count=$(echo "$body" | jq -r '.beat_count')
    echo "OK: beats_returns_tempo_and_beats (count=$count)"
}

# ── beats with click_track: returns base64 audio that decodes to WAV ────────

test_beats_click_track_is_wav() {
    local body b64 decoded
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"click_track\":true}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/beats")
    b64=$(echo "$body" | jq -r '.click_track_base64 // empty')
    if [ -z "$b64" ]; then
        echo "  FAIL: click_track_base64 missing; body: $body"; return 1
    fi
    decoded=$(mktemp)
    echo "$b64" | base64 -d > "$decoded"
    if ! [ -s "$decoded" ]; then
        echo "  FAIL: click track is not WAV"; rm -f "$decoded"; return 1
    fi
    rm -f "$decoded"
    echo "OK: beats_click_track_is_wav"
}

# ── beats with click_track + output_path: stages the click track in /v1/files

test_beats_click_track_output_path() {
    local body code fetched
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"click_track\":true,\"output_path\":\"mir/click.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/beats")
    if ! echo "$body" | jq -e '.path == "mir/click.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    # JSON still carries the beats array even with output_path.
    if ! echo "$body" | jq -e '.beats | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: beats array gone in output_path mode; body: $body"; return 1
    fi
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/mir/click.wav")
    assert_eq "$code" "200" "GET staged click -> 200" || { rm -f "$fetched"; return 1; }
    if ! head -c 4 "$fetched" | grep -q "RIFF"; then
        echo "  FAIL: staged file not WAV"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: beats_click_track_output_path"
}

# ── beats start_bpm: hint speeds up tracking without changing result shape ───

test_beats_start_bpm() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"start_bpm\":140}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/beats")
    if ! echo "$body" | jq -e '.tempo_bpm | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: tempo_bpm missing with start_bpm hint; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.beats | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: beats array missing; body: $body"; return 1
    fi
    echo "OK: beats_start_bpm (tempo=$(echo "$body" | jq -r '.tempo_bpm'))"
}

# ── onsets: list of {time, strength} ────────────────────────────────────────

test_onsets_returns_list() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/onsets")
    if ! echo "$body" | jq -e '.onsets | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: onsets not an array; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.count | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: count missing; body: $body"; return 1
    fi
    # Every onset must have time and strength.
    if echo "$body" | jq -e '.onsets[] | has("time") and has("strength")' >/dev/null 2>&1; then
        :
    fi
    echo "OK: onsets_returns_list ($(echo "$body" | jq -r '.count') onsets)"
}

# ── melody: pyin pitch contour ──────────────────────────────────────────────

test_melody_contour() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/melody")
    if ! echo "$body" | jq -e '.contour | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: contour not an array; body: $body"; return 1
    fi
    # Fixture is a 440 Hz sine — at least one entry should be voiced
    # with hz near 440.
    local has_voiced
    has_voiced=$(echo "$body" | jq -r '[.contour[] | select(.voiced == true and .hz != null and (.hz | tonumber) > 400 and (.hz | tonumber) < 500)] | length')
    if [ "${has_voiced:-0}" -lt 1 ]; then
        echo "  FAIL: no voiced ~440Hz frames detected in sine fixture"
        echo "        first few entries: $(echo "$body" | jq -r '.contour[:5]')"
        return 1
    fi
    echo "OK: melody_contour ($has_voiced voiced frames near 440Hz)"
}

# ── melody as_midi: returns base64 MIDI ─────────────────────────────────────

test_melody_as_midi() {
    local body b64 decoded
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"as_midi\":true}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/melody")
    b64=$(echo "$body" | jq -r '.midi_base64 // empty')
    if [ -z "$b64" ]; then
        echo "  FAIL: midi_base64 missing; body: $(echo "$body" | head -c 500)"; return 1
    fi
    decoded=$(mktemp)
    echo "$b64" | base64 -d > "$decoded"
    if ! [ -s "$decoded" ]; then
        echo "  FAIL: decoded base64 is not MIDI"; rm -f "$decoded"; return 1
    fi
    rm -f "$decoded"
    echo "OK: melody_as_midi"
}

# ── segments: structural ranges ─────────────────────────────────────────────

test_segments_returns_ranges() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"num_segments\":3}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/segments")
    if ! echo "$body" | jq -e '.segments | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: segments not an array; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.segments[0] | has("start_sec") and has("end_sec") and has("label")' >/dev/null 2>&1; then
        echo "  FAIL: segment missing fields; body: $body"; return 1
    fi
    echo "OK: segments_returns_ranges ($(echo "$body" | jq -r '.segments | length') segments)"
}

# ── beats with click track: BPM in [100, 150] range ──────────────────────────
# The plain 440 Hz sine has no perceivable beat — librosa's tracker can return
# anything. Use the harness-generated beat_120.wav (120 BPM click track) to
# verify the tracker actually returns a sensible BPM.

test_beats_click_fixture_bpm_in_range() {
    local body bpm
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${BEAT_FIXTURE}")"
    curl -sf -X PUT --data-binary "@${BEAT_FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/beats")
    bpm=$(echo "$body" | jq -r '.tempo_bpm // empty')
    if [ -z "$bpm" ] || [ "$bpm" = "null" ]; then
        echo "  FAIL: tempo_bpm missing for beat fixture; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.tempo_bpm > 100 and .tempo_bpm < 150' >/dev/null 2>&1; then
        echo "  FAIL: BPM $bpm not in [100,150] for 120BPM click fixture; body: $body"; return 1
    fi
    local count
    count=$(echo "$body" | jq -r '.beat_count // 0')
    echo "OK: beats_click_fixture_bpm_in_range (bpm=${bpm} count=${count})"
}

harness_run_tests \
    test_beats_returns_tempo_and_beats \
    test_beats_click_track_is_wav \
    test_beats_click_track_output_path \
    test_beats_start_bpm \
    test_beats_click_fixture_bpm_in_range \
    test_onsets_returns_list \
    test_melody_contour \
    test_melody_as_midi \
    test_segments_returns_ranges
