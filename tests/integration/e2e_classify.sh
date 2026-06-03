#!/bin/bash
# Zero-shot audio classification via CLAP — /v1/audio/classify end-to-end.
#
#     bash tests/integration/e2e_classify.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"
LABELS_JSON='["sine wave","music","speech","silence","noise"]'

harness_start "clap-embed"

# ── returns results array ─────────────────────────────────────────────────────

test_classify_returns_results() {
    local body
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "labels=${LABELS_JSON}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/classify")
    if ! echo "$body" | jq -e '.results | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: results not an array; body: $(echo "$body" | head -c 300)"
        return 1
    fi
    echo "OK: classify_returns_results"
}

# ── result count equals label count ──────────────────────────────────────────

test_classify_result_count_matches_labels() {
    local body n_labels n_results
    n_labels=$(echo "$LABELS_JSON" | python3 -c "import json,sys; print(len(json.load(sys.stdin)))")
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "labels=${LABELS_JSON}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/classify")
    n_results=$(echo "$body" | jq '.results | length')
    assert_eq "$n_results" "$n_labels" "result count == label count" || return 1
    echo "OK: classify_result_count_matches_labels (${n_results} results)"
}

# ── each result has label (string) and score (number) ────────────────────────

test_classify_result_schema() {
    local body ok
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "labels=${LABELS_JSON}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/classify")
    ok=$(echo "$body" | python3 -c "
import json, sys
data = json.load(sys.stdin)
results = data.get('results', [])
for r in results:
    assert isinstance(r.get('label'), str), 'label not string'
    assert isinstance(r.get('score'), (int, float)), 'score not number'
print('ok')
" 2>&1)
    if [ "$ok" != "ok" ]; then
        echo "  FAIL: schema check: $ok"; return 1
    fi
    echo "OK: classify_result_schema"
}

# ── results are sorted by score descending ───────────────────────────────────

test_classify_sorted_descending() {
    local body ok
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "labels=${LABELS_JSON}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/classify")
    ok=$(echo "$body" | python3 -c "
import json, sys
results = json.load(sys.stdin).get('results', [])
scores = [r['score'] for r in results]
print('ok' if scores == sorted(scores, reverse=True) else 'fail: ' + str(scores))
")
    if [ "$ok" != "ok" ]; then
        echo "  FAIL: $ok"; return 1
    fi
    echo "OK: classify_sorted_descending"
}

# ── single label works ────────────────────────────────────────────────────────

test_classify_single_label() {
    local body n
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F 'labels=["sine wave"]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/classify")
    n=$(echo "$body" | jq '.results | length')
    assert_eq "$n" "1" "single label -> 1 result" || return 1
    echo "OK: classify_single_label"
}

# ── missing labels → 422 (required field) ────────────────────────────────────

test_classify_missing_labels_422() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/classify")
    assert_eq "$code" "422" "missing labels -> 422" || return 1
    echo "OK: classify_missing_labels_422"
}

# ── invalid JSON labels → 400 ────────────────────────────────────────────────

test_classify_invalid_labels_json_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "labels=not-json" \
        "${AUDIOLLA_BASE_URL}/v1/audio/classify")
    assert_eq "$code" "400" "invalid JSON labels -> 400" || return 1
    echo "OK: classify_invalid_labels_json_400"
}

# ── empty labels array → 400 ─────────────────────────────────────────────────

test_classify_empty_labels_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "labels=[]" \
        "${AUDIOLLA_BASE_URL}/v1/audio/classify")
    assert_eq "$code" "400" "empty labels -> 400" || return 1
    echo "OK: classify_empty_labels_400"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_classify_missing_file_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        -F "labels=${LABELS_JSON}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/classify")
    assert_eq "$code" "400" "missing file -> 400" || return 1
    echo "OK: classify_missing_file_400"
}

harness_run_tests \
    test_classify_returns_results \
    test_classify_result_count_matches_labels \
    test_classify_result_schema \
    test_classify_sorted_descending \
    test_classify_single_label \
    test_classify_missing_labels_422 \
    test_classify_invalid_labels_json_400 \
    test_classify_empty_labels_400 \
    test_classify_missing_file_400
