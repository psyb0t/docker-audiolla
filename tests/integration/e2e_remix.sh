#!/bin/bash
# Remix endpoint — /v1/audio/remix (stem separate + gain-mix bounce).
# The happy path requires a separation engine (htdemucs) which is GPU-only.
# These tests cover error paths that fail before any model inference, so they
# run against the CPU image with only librosa-analyze loaded.
#
#     bash tests/integration/e2e_remix.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── unknown engine → 404 ─────────────────────────────────────────────────────

test_remix_unknown_engine_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=no-such-engine" \
        "${AUDIOLLA_BASE_URL}/v1/audio/remix")
    assert_eq "$code" "404" "unknown engine -> 404" || return 1
    echo "OK: remix_unknown_engine_404"
}

# ── non-separation engine → 400 ──────────────────────────────────────────────
# librosa-analyze is loaded but it's not a separation engine.

test_remix_non_separation_engine_400() {
    local code body
    body=$(curl -s --max-time 30 -o /dev/null -w "%{http_code}" -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=librosa-analyze" \
        "${AUDIOLLA_BASE_URL}/v1/audio/remix")
    assert_eq "$body" "400" "non-separation engine -> 400" || return 1
    echo "OK: remix_non_separation_engine_400"
}

# ── invalid stem_mix JSON → 400 ──────────────────────────────────────────────

test_remix_invalid_stem_mix_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=librosa-analyze" \
        -F "stem_mix=not-json{{{" \
        "${AUDIOLLA_BASE_URL}/v1/audio/remix")
    assert_eq "$code" "400" "invalid stem_mix JSON -> 400" || return 1
    echo "OK: remix_invalid_stem_mix_400"
}

# ── stem_mix must be object (not array) → 400 ────────────────────────────────

test_remix_stem_mix_array_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=librosa-analyze" \
        -F 'stem_mix=["vocals","drums"]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/remix")
    assert_eq "$code" "400" "stem_mix as array -> 400" || return 1
    echo "OK: remix_stem_mix_array_400"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_remix_missing_file_path_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X POST \
        -F "file_path=nosuch/audio.wav" \
        -F "engine=librosa-analyze" \
        "${AUDIOLLA_BASE_URL}/v1/audio/remix")
    assert_eq "$code" "404" "missing file_path -> 404" || return 1
    echo "OK: remix_missing_file_path_404"
}

harness_run_tests \
    test_remix_unknown_engine_404 \
    test_remix_non_separation_engine_400 \
    test_remix_invalid_stem_mix_400 \
    test_remix_stem_mix_array_400 \
    test_remix_missing_file_path_404
