#!/bin/bash
# Audio thumbnail extraction — /v1/audio/thumbnail.
#
#     bash tests/integration/e2e_thumbnail.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── default 30s: fixture is 8s, so entire file returned ──────────────────────

test_thumbnail_short_file_returns_whole() {
    local tmpf code sz
    tmpf=$(mktemp --suffix=.wav)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/thumbnail")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "thumbnail default -> 200" || { rm -f "$tmpf"; return 1; }
    if [ "$(stat -c%s "$tmpf")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"; rm -f "$tmpf"; return 1
    fi
    sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    if [ "$sz" -lt 100000 ]; then
        echo "  FAIL: output too small ($sz bytes)"; return 1
    fi
    echo "OK: thumbnail_short_file_returns_whole (${sz}B)"
}

# ── duration_sec=4: segment is ~4s of 8s file ────────────────────────────────

test_thumbnail_4s_from_8s_file() {
    local tmpf code info_body dur
    tmpf=$(mktemp --suffix=.wav)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"duration_sec\":4,\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/thumbnail")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "thumbnail 4s -> 200" || { rm -f "$tmpf"; return 1; }
    # Check duration via /v1/audio/info
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${tmpf}")"
    curl -sf -X PUT --data-binary "@${tmpf}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    info_body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info")
    rm -f "$tmpf"
    dur=$(echo "$info_body" | jq -r '.duration_sec // empty')
    if [ -z "$dur" ]; then
        echo "  FAIL: could not get duration from info; body: $info_body"; return 1
    fi
    if ! echo "$info_body" | jq -e '.duration_sec >= 3.5 and .duration_sec <= 5.0' >/dev/null 2>&1; then
        echo "  FAIL: thumbnail duration $dur not in [3.5, 5.0]"; return 1
    fi
    echo "OK: thumbnail_4s_from_8s_file (dur=${dur}s)"
}

# ── output_path returns JSON with start_sec/end_sec ──────────────────────────

test_thumbnail_output_path_metadata() {
    local body code fetched
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"duration_sec\":4,\"output_path\":\"thumb_test/segment.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/thumbnail")
    if ! echo "$body" | jq -e '.path == "thumb_test/segment.wav"' >/dev/null 2>&1; then
        echo "  FAIL: path missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e 'has("start_sec") and has("end_sec")' >/dev/null 2>&1; then
        echo "  FAIL: start_sec/end_sec missing from output_path response; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.start_sec >= 0 and .end_sec > .start_sec' >/dev/null 2>&1; then
        echo "  FAIL: invalid start/end; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/thumb_test/segment.wav")
    assert_eq "$code" "200" "GET staged thumbnail -> 200" || { rm -f "$fetched"; return 1; }
    if ! head -c 4 "$fetched" | grep -q "RIFF"; then
        echo "  FAIL: staged file not WAV"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    local start end
    start=$(echo "$body" | jq -r '.start_sec')
    end=$(echo "$body" | jq -r '.end_sec')
    echo "OK: thumbnail_output_path_metadata (start=$start end=$end)"
}

# ── mp3 output ────────────────────────────────────────────────────────────────

test_thumbnail_output_format_mp3() {
    local code tmpf
    tmpf=$(mktemp --suffix=.mp3)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"duration_sec\":4,\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$tmpf" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/thumbnail")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpf" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "thumbnail mp3 -> 200" || { rm -f "$tmpf"; return 1; }
    if [ ! -s "$tmpf" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpf"; return 1
    fi
    rm -f "$tmpf"
    echo "OK: thumbnail_output_format_mp3"
}

# ── duration_sec out of range → 400 ──────────────────────────────────────────

test_thumbnail_invalid_duration_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"duration_sec\":0,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/thumbnail")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] && echo "  OK: $duration_sec=0 -> 422 (code=$code)" || { echo "  FAIL: $duration_sec=0 -> 422 expected 400 or 422, got $code"; return 1; } || return 1
    echo "OK: thumbnail_invalid_duration_400"
}

harness_run_tests \
    test_thumbnail_short_file_returns_whole \
    test_thumbnail_4s_from_8s_file \
    test_thumbnail_output_path_metadata \
    test_thumbnail_output_format_mp3 \
    test_thumbnail_invalid_duration_400
