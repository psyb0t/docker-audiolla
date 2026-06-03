#!/bin/bash
# Audio embedding — /v1/audio/embed (CLAP engine).
#
#     bash tests/integration/e2e_embed.sh
#
# Requires the CLAP model (~250 MB) to be present in .e2e-cache/hf.
# Pre-populate on first run:
#
#     docker run --rm -v "$PWD/.e2e-cache:/data" \
#       -e HF_HUB_OFFLINE=0 -e AUDIOLLA_ENABLED_ENGINES=clap-embed \
#       -p 18999:8000 psyb0t/audiolla:local

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "clap-embed"

# ── basic: returns 512-dim embedding ─────────────────────────────────────────

test_embed_returns_embedding() {
    local body dim
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/embed")
    if ! echo "$body" | jq -e '.embedding | type == "array" and length > 0' >/dev/null 2>&1; then
        echo "  FAIL: embedding missing or empty; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.dim | type == "number" and . > 0' >/dev/null 2>&1; then
        echo "  FAIL: dim missing or not positive; body: $body"; return 1
    fi
    dim=$(echo "$body" | jq -r '.dim')
    if [ "$dim" -ne 512 ]; then
        echo "  FAIL: expected dim=512, got $dim"; return 1
    fi
    echo "OK: embed_returns_embedding (dim=$dim)"
}

# ── embedding is L2-normalised (norm ≈ 1.0) ──────────────────────────────────

test_embed_l2_norm() {
    local body norm
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/embed")
    if ! echo "$body" | jq -e '.embedding | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: no embedding; body: $body"; return 1
    fi
    norm=$(echo "$body" | python3 -c "
import json, sys, math
data = json.load(sys.stdin)
v = data['embedding']
n = math.sqrt(sum(x*x for x in v))
print(round(n, 4))
" 2>/dev/null || echo "0")
    if ! python3 -c "import sys; sys.exit(0 if abs(float('$norm') - 1.0) < 0.01 else 1)" 2>/dev/null; then
        echo "  FAIL: L2 norm is $norm (expected ~1.0)"; return 1
    fi
    echo "OK: embed_l2_norm (norm=$norm)"
}

# ── query_text: returns similarity score ─────────────────────────────────────

test_embed_query_text_similarity() {
    local body
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "query_text=sine wave tone" \
        "${AUDIOLLA_BASE_URL}/v1/audio/embed")
    if ! echo "$body" | jq -e '.similarity | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: similarity missing with query_text; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.query_text | type == "string" and length > 0' >/dev/null 2>&1; then
        echo "  FAIL: query_text echo missing; body: $body"; return 1
    fi
    local sim
    sim=$(echo "$body" | jq -r '.similarity')
    echo "OK: embed_query_text_similarity (similarity=$sim)"
}

# ── similarity is in [-1, 1] ─────────────────────────────────────────────────

test_embed_similarity_range() {
    local body sim
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "query_text=music" \
        "${AUDIOLLA_BASE_URL}/v1/audio/embed")
    if ! echo "$body" | jq -e '.similarity | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: no similarity; body: $body"; return 1
    fi
    sim=$(echo "$body" | jq -r '.similarity')
    if ! python3 -c "import sys; sys.exit(0 if -1.0 <= float('$sim') <= 1.0 else 1)" 2>/dev/null; then
        echo "  FAIL: similarity $sim out of [-1,1]"; return 1
    fi
    echo "OK: embed_similarity_range (sim=$sim)"
}

# ── missing file → 4xx ───────────────────────────────────────────────────────

test_embed_rejects_missing_file() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        "${AUDIOLLA_BASE_URL}/v1/audio/embed")
    if [ "$code" -lt 400 ] || [ "$code" -ge 500 ]; then
        echo "  FAIL: expected 4xx, got $code"; return 1
    fi
    echo "OK: embed_rejects_missing_file (HTTP $code)"
}

harness_run_tests \
    test_embed_returns_embedding \
    test_embed_l2_norm \
    test_embed_query_text_similarity \
    test_embed_similarity_range \
    test_embed_rejects_missing_file
