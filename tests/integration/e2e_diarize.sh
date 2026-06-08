#!/bin/bash
# Speaker diarization — /v1/audio/diarize/{engine}.
#
#     bash tests/integration/e2e_diarize.sh
#
# Requires HUGGINGFACE_TOKEN in tests/.env or the environment.

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

# Load HUGGINGFACE_TOKEN from tests/.env if it exists.
[ -f "$(dirname "$0")/../.env" ] && source "$(dirname "$0")/../.env"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "pyannote"

# ── basic: returns segments + num_speakers ───────────────────────────────────

test_diarize_returns_segments() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/diarize/pyannote")
    if ! echo "$body" | jq -e '.segments | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: segments not an array; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.num_speakers | type == "number" and . >= 1' >/dev/null 2>&1; then
        echo "  FAIL: num_speakers missing or < 1; body: $body"; return 1
    fi
    echo "OK: diarize_returns_segments (num_speakers=$(echo "$body" | jq -r '.num_speakers'))"
}

# ── unknown engine → 404 ─────────────────────────────────────────────────────

test_diarize_404_for_unknown_engine() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/diarize/nonexistent")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "404" "unknown engine -> 404" || return 1
    echo "OK: diarize_404_for_unknown_engine"
}

# ── num_speakers hint ────────────────────────────────────────────────────────

test_diarize_with_num_speakers() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"num_speakers\":2}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/diarize/pyannote")
    if ! echo "$body" | jq -e '.segments | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: segments missing when num_speakers=2; body: $body"; return 1
    fi
    echo "OK: diarize_with_num_speakers"
}

harness_run_tests \
    test_diarize_returns_segments \
    test_diarize_404_for_unknown_engine \
    test_diarize_with_num_speakers
