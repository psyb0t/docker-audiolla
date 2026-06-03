#!/bin/bash
# Audio similarity — /v1/audio/similar end-to-end.
#
#     bash tests/integration/e2e_similar.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"
FIXTURE_REF="${_DIR}/.fixtures/audio_ref.wav"

harness_start "clap-embed"

# ── similarity score present, in [-1,1] ──────────────────────────────────────

test_similar_returns_score() {
    local body sim
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "reference_file=@${FIXTURE_REF}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/similar")
    sim=$(echo "$body" | jq -r '.similarity // empty')
    if [ -z "$sim" ]; then
        echo "  FAIL: no similarity field; body: $body"; return 1
    fi
    local ok
    ok=$(python3 -c "
s = float('${sim}')
print('ok' if -1.0 <= s <= 1.0 else 'fail (similarity={})'.format(s))
")
    if [ "$ok" != "ok" ]; then
        echo "  FAIL: $ok"; return 1
    fi
    echo "OK: similar_returns_score (similarity=${sim})"
}

# ── same file with itself → high similarity ───────────────────────────────────

test_similar_self_is_high() {
    local body sim
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "reference_file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/similar")
    sim=$(echo "$body" | jq -r '.similarity // empty')
    if [ -z "$sim" ]; then
        echo "  FAIL: no similarity field; body: $body"; return 1
    fi
    local ok
    ok=$(python3 -c "
s = float('${sim}')
print('ok' if s > 0.9 else 'fail (self-similarity={:.4f} expected > 0.9)'.format(s))
")
    if [ "$ok" != "ok" ]; then
        echo "  FAIL: $ok"; return 1
    fi
    echo "OK: similar_self_is_high (similarity=${sim})"
}

# ── dim field present ─────────────────────────────────────────────────────────

test_similar_dim_field() {
    local body dim
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "reference_file=@${FIXTURE_REF}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/similar")
    dim=$(echo "$body" | jq -r '.dim // empty')
    if [ -z "$dim" ] || [ "$dim" = "0" ]; then
        echo "  FAIL: missing or zero dim field; body: $body"; return 1
    fi
    echo "OK: similar_dim_field (dim=${dim})"
}

# ── missing reference → 400 ───────────────────────────────────────────────────

test_similar_missing_reference_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/similar")
    assert_eq "$code" "400" "missing reference -> 400" || return 1
    echo "OK: similar_missing_reference_400"
}

# ── missing primary file → 400 ───────────────────────────────────────────────

test_similar_missing_primary_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        -F "reference_file=@${FIXTURE_REF}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/similar")
    assert_eq "$code" "404" "missing primary -> 404" || return 1
    echo "OK: similar_missing_primary_404"
}

harness_run_tests \
    test_similar_returns_score \
    test_similar_self_is_high \
    test_similar_dim_field \
    test_similar_missing_reference_400 \
    test_similar_missing_primary_404
