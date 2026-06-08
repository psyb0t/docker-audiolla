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
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${FIXTURE_REF}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${FIXTURE_REF}")" >/dev/null || true
    local body sim
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"reference_file_path\":\"secondary/$(basename "${FIXTURE_REF}")\"}" \
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
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${FIXTURE}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${FIXTURE}")" >/dev/null || true
    local body sim
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"reference_file_path\":\"secondary/$(basename "${FIXTURE}")\"}" \
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
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${FIXTURE_REF}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${FIXTURE_REF}")" >/dev/null || true
    local body dim
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"reference_file_path\":\"secondary/$(basename "${FIXTURE_REF}")\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/similar")
    dim=$(echo "$body" | jq -r '.dim // empty')
    if [ -z "$dim" ] || [ "$dim" = "0" ]; then
        echo "  FAIL: missing or zero dim field; body: $body"; return 1
    fi
    echo "OK: similar_dim_field (dim=${dim})"
}

# ── missing reference → 400 ───────────────────────────────────────────────────

test_similar_missing_reference_422() {
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
        "${AUDIOLLA_BASE_URL}/v1/audio/similar")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] || { echo "  FAIL: missing reference -> got $code"; return 1; }
    echo "OK: similar_missing_reference_422 (code=$code)"
}

# ── missing primary file → 400 ───────────────────────────────────────────────

test_similar_missing_primary_404() {
    # v1.0.0 secondary fixture stage
    curl -sf -X PUT --data-binary "@${FIXTURE_REF}" -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/secondary/$(basename "${FIXTURE_REF}")" >/dev/null || true
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"no/such.wav\",\"reference_file_path\":\"secondary/$(basename "${FIXTURE_REF}")\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/similar")
    [[ "$code" = "400" || "$code" = "404" || "$code" = "422" || "$code" = "500" ]] || { echo "  FAIL: missing primary -> got $code"; return 1; }
    echo "OK: similar_missing_primary_404 (code=$code)"
}

harness_run_tests \
    test_similar_returns_score \
    test_similar_self_is_high \
    test_similar_dim_field \
    test_similar_missing_reference_422 \
    test_similar_missing_primary_404
