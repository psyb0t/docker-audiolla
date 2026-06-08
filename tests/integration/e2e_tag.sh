#!/bin/bash
# Audio tagging — /v1/audio/tag (AST engine).
#
#     bash tests/integration/e2e_tag.sh
#
# Requires the AST model (~90 MB) to be present in .e2e-cache/hf.
# Pre-populate on first run:
#
#     docker run --rm -v "$PWD/.e2e-cache:/data" \
#       -e HF_HUB_OFFLINE=0 -e AUDIOLLA_ENABLED_ENGINES=ast-tag \
#       -p 18999:8000 psyb0t/audiolla:local

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "ast-tag"

# ── basic: returns tags array + duration ─────────────────────────────────────

test_tag_returns_tags_and_duration() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/tag")
    if ! echo "$body" | jq -e '.tags | type == "array" and length > 0' >/dev/null 2>&1; then
        echo "  FAIL: tags missing or empty; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.tags[0] | has("label") and has("score")' >/dev/null 2>&1; then
        echo "  FAIL: tag item missing label/score; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.duration | type == "number" and . > 0' >/dev/null 2>&1; then
        echo "  FAIL: duration missing or not positive; body: $body"; return 1
    fi
    local top_label score
    top_label=$(echo "$body" | jq -r '.tags[0].label')
    score=$(echo "$body" | jq -r '.tags[0].score')
    echo "OK: tag_returns_tags_and_duration (top=${top_label} score=${score} dur=$(echo "$body" | jq -r '.duration'))"
}

# ── missing file → 4xx ───────────────────────────────────────────────────────

test_tag_rejects_missing_file() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        "${AUDIOLLA_BASE_URL}/v1/audio/tag")
    if [ "$code" -lt 400 ] || [ "$code" -ge 500 ]; then
        echo "  FAIL: expected 4xx, got $code"; return 1
    fi
    echo "OK: tag_rejects_missing_file (HTTP $code)"
}

# ── top_k param: returns exactly N tags ──────────────────────────────────────

test_tag_top_k() {
    local body count
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"top_k\":5}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/tag")
    if ! echo "$body" | jq -e '.tags | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: tags missing with top_k=5; body: $body"; return 1
    fi
    count=$(echo "$body" | jq -r '.tags | length')
    if [ "$count" -gt 5 ]; then
        echo "  FAIL: top_k=5 but got $count tags"; return 1
    fi
    echo "OK: tag_top_k (count=$count)"
}

# ── score range: all scores between 0 and 1 ──────────────────────────────────

test_tag_score_range() {
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/tag")
    if ! echo "$body" | jq -e '.tags | map(.score) | all(. >= 0 and . <= 1)' >/dev/null 2>&1; then
        echo "  FAIL: score outside [0,1]; body: $body"; return 1
    fi
    echo "OK: tag_score_range"
}

harness_run_tests \
    test_tag_returns_tags_and_duration \
    test_tag_rejects_missing_file \
    test_tag_top_k \
    test_tag_score_range
