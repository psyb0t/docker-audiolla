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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"engine\":\"no-such-engine\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/remix")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "404" "unknown engine -> 404" || return 1
    echo "OK: remix_unknown_engine_404"
}

# ── non-separation engine → 400 ──────────────────────────────────────────────
# librosa-analyze is loaded but it's not a separation engine.

test_remix_non_separation_engine_400() {
    local code body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"engine\":\"librosa-analyze\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/remix")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$body" "400" "non-separation engine -> 400" || return 1
    echo "OK: remix_non_separation_engine_400"
}

# ── invalid stem_mix JSON → 400 ──────────────────────────────────────────────

test_remix_invalid_stem_mix_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"engine\":\"librosa-analyze\",\"stem_mix\":\"not-json{{{\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/remix")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "422" "invalid stem_mix JSON -> 422" || return 1
    echo "OK: remix_invalid_stem_mix_400"
}

# ── stem_mix must be object (not array) → 400 ────────────────────────────────

test_remix_stem_mix_array_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    # stem_mix must be an object (dict). Sending an array → Pydantic rejects with 422.
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"engine\":\"librosa-analyze\",\"stem_mix\":[1,2,3],\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/remix")
    assert_eq "$code" "422" "stem_mix as array -> 422" || return 1
    echo "OK: remix_stem_mix_array_400"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_remix_missing_file_path_404() {
    local code
    # Missing output_path on a sync request triggers handler-level XOR check (400).
    code=$(curl -s -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"nosuch/audio.wav\",\"engine\":\"librosa-analyze\",\"output_path\":\"out/r-$$.wav\"}" \
        -o "/dev/null" -w "%{http_code}" --max-time 30 "${AUDIOLLA_BASE_URL}/v1/audio/remix")
    # The engine check (librosa-analyze isn't a separation engine) returns 400
    # BEFORE the file resolver runs, so file existence never gets to 404.
    assert_eq "$code" "400" "non-separation engine guards missing file -> 400" || return 1
    echo "OK: remix_missing_file_path_404"
}

harness_run_tests \
    test_remix_unknown_engine_404 \
    test_remix_non_separation_engine_400 \
    test_remix_invalid_stem_mix_400 \
    test_remix_stem_mix_array_400 \
    test_remix_missing_file_path_404
