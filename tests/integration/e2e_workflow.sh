#!/bin/bash
# Discoverability + workflow endpoints — /v1/catalog, /v1/ops, /v1/presets,
# /v1/pipeline.
#
#     bash tests/integration/e2e_workflow.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

# Presets / pipeline use ops that touch librosa-analyze (for normalize) +
# fx-chain (for fx). Both are cheap to boot.
harness_start "librosa-analyze,fx-chain"

# ── /v1/catalog returns categories with endpoints ────────────────────────────

test_catalog_returns_categories() {
    local body
    body=$(curl -s --max-time 10 "${AUDIOLLA_BASE_URL}/v1/catalog")
    if ! echo "$body" | jq -e '.object == "catalog"' >/dev/null 2>&1; then
        echo "  FAIL: missing object=catalog; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.categories | type == "array" and length > 5' >/dev/null 2>&1; then
        echo "  FAIL: categories not array or too few; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.categories[] | select(.name == "workflow")' >/dev/null 2>&1; then
        echo "  FAIL: workflow category missing"; return 1
    fi
    if ! echo "$body" | jq -e '.categories[] | select(.name == "dynamics") | .endpoints | length > 0' >/dev/null 2>&1; then
        echo "  FAIL: dynamics category empty"; return 1
    fi
    echo "OK: catalog_returns_categories"
}

# ── /v1/ops returns a non-empty op list ──────────────────────────────────────

test_ops_returns_list() {
    local body
    body=$(curl -s --max-time 10 "${AUDIOLLA_BASE_URL}/v1/ops")
    if ! echo "$body" | jq -e '.object == "list"' >/dev/null 2>&1; then
        echo "  FAIL: missing object=list; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.data | type == "array" and length > 10' >/dev/null 2>&1; then
        echo "  FAIL: data not a list or too few ops; body: $body"; return 1
    fi
    for op in trim eq normalize multiband_compress fx; do
        if ! echo "$body" | jq -e --arg op "$op" '.data | index($op)' >/dev/null 2>&1; then
            echo "  FAIL: op $op missing from /v1/ops"; return 1
        fi
    done
    echo "OK: ops_returns_list ($(echo "$body" | jq '.data | length') ops)"
}

# ── /v1/presets lists curated presets ────────────────────────────────────────

test_presets_list() {
    local body
    body=$(curl -s --max-time 10 "${AUDIOLLA_BASE_URL}/v1/presets")
    if ! echo "$body" | jq -e '.data | length >= 3' >/dev/null 2>&1; then
        echo "  FAIL: expected >=3 presets; body: $body"; return 1
    fi
    for name in podcast-cleanup master-for-spotify vocal-cleanup; do
        if ! echo "$body" | jq -e --arg n "$name" '.data | map(.name) | index($n)' >/dev/null 2>&1; then
            echo "  FAIL: preset $name missing"; return 1
        fi
    done
    echo "OK: presets_list"
}

# ── /v1/presets/{name} describes a preset ───────────────────────────────────

test_presets_describe() {
    local body
    body=$(curl -s --max-time 10 "${AUDIOLLA_BASE_URL}/v1/presets/master-for-spotify")
    if ! echo "$body" | jq -e '.name == "master-for-spotify"' >/dev/null 2>&1; then
        echo "  FAIL: name field wrong; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.steps | length >= 2' >/dev/null 2>&1; then
        echo "  FAIL: expected >=2 steps; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.steps[0].op == "multiband_compress"' >/dev/null 2>&1; then
        echo "  FAIL: first step should be multiband_compress; body: $body"; return 1
    fi
    echo "OK: presets_describe"
}

# ── /v1/presets/{name} unknown → 404 ───────────────────────────────────────

test_presets_describe_unknown_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
        "${AUDIOLLA_BASE_URL}/v1/presets/does-not-exist")
    assert_eq "$code" "404" "unknown preset -> 404" || return 1
    echo "OK: presets_describe_unknown_404"
}

# ── /v1/pipeline runs a 2-step ad-hoc chain ─────────────────────────────────

test_pipeline_run_2step() {
    local code tmpf in_sz out_sz
    tmpf=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$tmpf" -w "%{http_code}" --max-time 90 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'steps=[{"op":"reverse","params":{}},{"op":"trim","params":{"end_sec":2.0}}]' \
        "${AUDIOLLA_BASE_URL}/v1/pipeline")
    assert_eq "$code" "200" "pipeline -> 200" || { rm -f "$tmpf"; return 1; }
    if ! head -c 4 "$tmpf" | grep -q "RIFF"; then
        echo "  FAIL: pipeline output is not WAV"; rm -f "$tmpf"; return 1
    fi
    in_sz=$(stat -c%s "$FIXTURE")
    out_sz=$(stat -c%s "$tmpf")
    rm -f "$tmpf"
    # Trim to 2s of 44.1k stereo ≈ 350 KB
    if [ "$out_sz" -lt 100000 ] || [ "$out_sz" -gt "$in_sz" ]; then
        echo "  FAIL: trimmed output size ($out_sz) implausible vs input ($in_sz)"; return 1
    fi
    echo "OK: pipeline_run_2step (in=$in_sz out=$out_sz)"
}

# ── /v1/pipeline + output_path stages result + returns step log ─────────────

test_pipeline_output_path_step_log() {
    local body
    body=$(curl -s --max-time 90 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'steps=[{"op":"reverse","params":{}}]' \
        -F "output_path=pipe_test/out.wav" \
        "${AUDIOLLA_BASE_URL}/v1/pipeline")
    if ! echo "$body" | jq -e '.path == "pipe_test/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    if ! echo "$body" | jq -e '.steps | length == 1 and .[0].op == "reverse"' >/dev/null 2>&1; then
        echo "  FAIL: step_log missing/wrong; body: $body"; return 1
    fi
    echo "OK: pipeline_output_path_step_log"
}

# ── /v1/pipeline rejects unknown op → 400 ───────────────────────────────────

test_pipeline_unknown_op_400() {
    local code body
    body=$(curl -s -w "\n%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'steps=[{"op":"this-is-not-real","params":{}}]' \
        "${AUDIOLLA_BASE_URL}/v1/pipeline")
    code=$(echo "$body" | tail -n1)
    assert_eq "$code" "400" "unknown op -> 400" || return 1
    if ! echo "$body" | head -n-1 | grep -qi "unknown op"; then
        echo "  FAIL: error body should mention 'unknown op'"; return 1
    fi
    echo "OK: pipeline_unknown_op_400"
}

# ── /v1/pipeline rejects bad JSON in steps → 400 ────────────────────────────

test_pipeline_bad_json_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'steps=not-json' \
        "${AUDIOLLA_BASE_URL}/v1/pipeline")
    assert_eq "$code" "400" "bad steps JSON -> 400" || return 1
    echo "OK: pipeline_bad_json_400"
}

# ── /v1/pipeline empty steps → 400 ──────────────────────────────────────────

test_pipeline_empty_steps_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'steps=[]' \
        "${AUDIOLLA_BASE_URL}/v1/pipeline")
    assert_eq "$code" "400" "empty steps -> 400" || return 1
    echo "OK: pipeline_empty_steps_400"
}

# ── /v1/engines includes loaded + idle_seconds ──────────────────────────────

test_engines_includes_load_status() {
    local body
    body=$(curl -s --max-time 10 "${AUDIOLLA_BASE_URL}/v1/engines")
    if ! echo "$body" | jq -e '.data[0] | has("loaded") and has("idle_seconds")' >/dev/null 2>&1; then
        echo "  FAIL: missing loaded / idle_seconds; body: $(echo "$body" | head -c 300)"; return 1
    fi
    echo "OK: engines_includes_load_status"
}

harness_run_tests \
    test_catalog_returns_categories \
    test_ops_returns_list \
    test_presets_list \
    test_presets_describe \
    test_presets_describe_unknown_404 \
    test_pipeline_run_2step \
    test_pipeline_output_path_step_log \
    test_pipeline_unknown_op_400 \
    test_pipeline_bad_json_400 \
    test_pipeline_empty_steps_400 \
    test_engines_includes_load_status
