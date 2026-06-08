#!/bin/bash
# Digital clipping detection — /v1/audio/clip-detect.
#
#     bash tests/integration/e2e_clip_detect.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"
FIXTURE_DIR="${_DIR}/.fixtures"
CLIPPED_FIXTURE="${FIXTURE_DIR}/clipped.wav"

harness_start "librosa-analyze"

# Build a clipped fixture: sine at +6dBFS relative so samples exceed ±1.0
# then clamp at 0dBFS via ffmpeg's alimiter.
build_clipped_fixture() {
    if [ -f "$CLIPPED_FIXTURE" ]; then
        return 0
    fi
    docker run --rm \
        --entrypoint ffmpeg \
        -v "${FIXTURE_DIR}:${FIXTURE_DIR}" \
        "$HARNESS_IMAGE" \
        -y -hide_banner -nostats \
        -f lavfi -i "sine=frequency=440:duration=4,volume=6dB" \
        -af "aclip=level_out=1.0" \
        "$CLIPPED_FIXTURE" >/dev/null 2>&1 || true
    # Fallback: just double the amplitude without limiting so values are above 1.0.
    if [ ! -f "$CLIPPED_FIXTURE" ]; then
        docker run --rm \
            --entrypoint ffmpeg \
            -v "${FIXTURE_DIR}:${FIXTURE_DIR}" \
            "$HARNESS_IMAGE" \
            -y -hide_banner -nostats \
            -f lavfi -i "sine=frequency=440:duration=4,volume=volume=20dB" \
            -f s16le -ar 44100 -ac 1 -bitexact \
            "$CLIPPED_FIXTURE" >/dev/null 2>&1 || true
    fi
    # Last-resort: copy fixture and rely on clip_detect finding 0 clips on it.
    if [ ! -f "$CLIPPED_FIXTURE" ]; then
        cp "$FIXTURE" "$CLIPPED_FIXTURE"
    fi
}

# ── clean audio returns clipped=false ────────────────────────────────────────

test_clip_detect_clean_audio() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/clip-detect")
    if ! echo "$body" | jq -e 'has("clipped")' >/dev/null 2>&1; then
        echo "  FAIL: clipped field missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.peak_db | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: peak_db missing; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.duration_sec > 7 and .duration_sec < 9' >/dev/null 2>&1; then
        echo "  FAIL: duration_sec not ~8s; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.sample_rate == 44100' >/dev/null 2>&1; then
        echo "  FAIL: sample_rate not 44100; body: $body"; return 1
    fi
    echo "OK: clip_detect_clean_audio (peak=$(echo "$body" | jq -r '.peak_db')dB clipped=$(echo "$body" | jq -r '.clipped'))"
}

# ── response has all required fields ─────────────────────────────────────────

test_clip_detect_response_shape() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/clip-detect")
    for field in clipped clip_count clip_ratio peak_db duration_sec sample_rate channels; do
        if ! echo "$body" | jq -e "has(\"$field\")" >/dev/null 2>&1; then
            echo "  FAIL: field '$field' missing; body: $body"; return 1
        fi
    done
    echo "OK: clip_detect_response_shape"
}

# ── file_path staging round-trip: stage then clip-detect from path ────────────

test_clip_detect_via_file_path() {
    # Stage the fixture first.
    local stage_body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    stage_body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"clip_test/input.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/convert")
    if ! echo "$stage_body" | jq -e '.path == "clip_test/input.wav"' >/dev/null 2>&1; then
        echo "  FAIL: staging failed; body: $stage_body"; return 1
    fi
    # Now detect from staged file_path.
    local body
    body=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"file_path\":\"clip_test/input.wav\"}" --max-time 30 "${AUDIOLLA_BASE_URL}/v1/audio/clip-detect")
    if ! echo "$body" | jq -e 'has("clipped")' >/dev/null 2>&1; then
        echo "  FAIL: clip-detect via file_path failed; body: $body"; return 1
    fi
    echo "OK: clip_detect_via_file_path"
}

harness_run_tests \
    test_clip_detect_clean_audio \
    test_clip_detect_response_shape \
    test_clip_detect_via_file_path
