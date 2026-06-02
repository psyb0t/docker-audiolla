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
    body=$(curl -s --max-time 300 -X POST \
        -F "file=@${FIXTURE}" \
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
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/diarize/nonexistent")
    assert_eq "$code" "404" "unknown engine -> 404" || return 1
    echo "OK: diarize_404_for_unknown_engine"
}

# ── num_speakers hint ────────────────────────────────────────────────────────

test_diarize_with_num_speakers() {
    local body
    body=$(curl -s --max-time 300 -X POST \
        -F "file=@${FIXTURE}" \
        -F "num_speakers=2" \
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
