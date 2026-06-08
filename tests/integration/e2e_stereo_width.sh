#!/bin/bash
# Stereo width — /v1/audio/stereo-width end-to-end.
#
#     bash tests/integration/e2e_stereo_width.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── default width=1.0 → 200 WAV ──────────────────────────────────────────────

test_stereo_width_default() {
    local tmpout code
    tmpout=$(mktemp)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "stereo-width default -> 200" || { rm -f "$tmpout"; return 1; }
    if [ "$(stat -c%s "$tmpout")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: stereo_width_default ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── width=0.0 (mono) → stereo output with both channels ──────────────────────

test_stereo_width_mono_collapse() {
    local body ch
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/sw-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":0.0,\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width" >/dev/null
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info")
    ch=$(echo "$body" | jq -r '.channels')
    # stereo_width always outputs stereo (via aformat=stereo in the pan filter)
    assert_eq "$ch" "2" "width=0.0 output channels=2" || return 1
    echo "OK: stereo_width_mono_collapse (channels=${ch})"
}

# ── width=2.0 (wide) accepted ─────────────────────────────────────────────────

test_stereo_width_wide() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":2.0,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "width=2.0 -> 200" || return 1
    echo "OK: stereo_width_wide"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_stereo_width_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":1.0,\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "stereo-width mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: stereo_width_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── width out of range → 400 ──────────────────────────────────────────────────

test_stereo_width_out_of_range_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":5.0,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] && echo "  OK: $width=5.0 -> 422 (code=$code)" || { echo "  FAIL: $width=5.0 -> 422 expected 400 or 422, got $code"; return 1; } || return 1
    echo "OK: stereo_width_out_of_range_400"
}

# ── negative width → 400 ─────────────────────────────────────────────────────

test_stereo_width_negative_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":-0.5,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] && echo "  OK: $width=-0.5 -> 422 (code=$code)" || { echo "  FAIL: $width=-0.5 -> 422 expected 400 or 422, got $code"; return 1; } || return 1
    echo "OK: stereo_width_negative_400"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_stereo_width_missing_file_404() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"no/such.wav\",\"output_path\":\"out/missing-$$.wav\"}" \
        -o "/dev/null" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: stereo_width_missing_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_stereo_width_output_path() {
    local body code tmpout
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":1.5,\"output_path\":\"stereo/wide.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    if ! echo "$body" | jq -e '.path == "stereo/wide.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/stereo/wide.wav")
    assert_eq "$code" "200" "GET staged stereo-width -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: stereo_width_output_path"
}

harness_run_tests \
    test_stereo_width_default \
    test_stereo_width_mono_collapse \
    test_stereo_width_wide \
    test_stereo_width_output_format_mp3 \
    test_stereo_width_out_of_range_400 \
    test_stereo_width_negative_400 \
    test_stereo_width_missing_file_404 \
    test_stereo_width_output_path
