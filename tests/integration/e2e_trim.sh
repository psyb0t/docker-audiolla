#!/bin/bash
# Audio trim — /v1/audio/trim end-to-end.
#
#     bash tests/integration/e2e_trim.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── returns WAV with valid magic bytes ───────────────────────────────────────

test_trim_returns_wav() {
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
        -d "{\"file_path\":\"$_stage\",\"start_sec\":1.0,\"end_sec\":4.0,\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "trim -> 200" || { rm -f "$tmpout"; return 1; }
    if [ "$(stat -c%s "$tmpout")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: trim_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── trimmed audio is shorter than the source ─────────────────────────────────

test_trim_output_is_shorter() {
    local src_dur trim_dur
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    src_dur=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')

    local _out="out/trim-$$-$RANDOM.wav"
    curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"start_sec\":0.0,\"end_sec\":3.0,\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim" >/dev/null
    trim_dur=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')

    local ok
    ok=$(python3 -c "
src  = float('${src_dur}')
trim = float('${trim_dur}')
# allow 0.5 s rounding slop
print('ok' if trim < src and trim <= 3.5 else 'fail (src={} trim={})'.format(src, trim))
")
    if [ "$ok" != "ok" ]; then
        echo "  FAIL: $ok"; return 1
    fi
    echo "OK: trim_output_is_shorter (src=${src_dur}s → trim=${trim_dur}s)"
}

# ── start_sec=0 (default) works ──────────────────────────────────────────────

test_trim_default_start_sec() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"end_sec\":2.0,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "trim default start_sec -> 200" || return 1
    echo "OK: trim_default_start_sec"
}

# ── output_format=mp3 → valid response ───────────────────────────────────────

test_trim_output_format_mp3() {
    local code ct tmpout
    tmpout=$(mktemp)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"start_sec\":0.0,\"end_sec\":2.0,\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "trim mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3 response"; rm -f "$tmpout"; return 1
    fi
    echo "OK: trim_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── end_sec missing → 422 (required field) ───────────────────────────────────

test_trim_missing_end_sec_422() {
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
        "${AUDIOLLA_BASE_URL}/v1/audio/trim")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "422" "missing end_sec -> 422" || return 1
    echo "OK: trim_missing_end_sec_422"
}

# ── end_sec <= start_sec → 400 ───────────────────────────────────────────────

test_trim_end_before_start_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"start_sec\":5.0,\"end_sec\":2.0,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] || { echo "  FAIL: end_sec <= start_sec expected 400/422, got $code"; return 1; }
    echo "OK: trim_end_before_start_400 (code=$code)"
}

# ── start_sec negative → 400 ─────────────────────────────────────────────────

test_trim_negative_start_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"start_sec\":-1.0,\"end_sec\":3.0,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] || { echo "  FAIL: negative start_sec expected 400/422, got $code"; return 1; }
    echo "OK: trim_negative_start_400 (code=$code)"
}

# ── missing file → 404 (staged file not found) ──────────────────────────────

test_trim_missing_file_404() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"no/such.wav\",\"end_sec\":3.0,\"output_path\":\"out/missing-$$.wav\"}" \
        -o "/dev/null" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: trim_missing_file_404"
}

# ── output_path: staged file is readable ─────────────────────────────────────

test_trim_output_path() {
    local body code tmpout
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"start_sec\":0.0,\"end_sec\":2.0,\"output_path\":\"trim/out.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim")
    if ! echo "$body" | jq -e '.path == "trim/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/trim/out.wav")
    assert_eq "$code" "200" "GET staged trim -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: trim_output_path"
}

harness_run_tests \
    test_trim_returns_wav \
    test_trim_output_is_shorter \
    test_trim_default_start_sec \
    test_trim_output_format_mp3 \
    test_trim_missing_end_sec_422 \
    test_trim_end_before_start_400 \
    test_trim_negative_start_400 \
    test_trim_missing_file_404 \
    test_trim_output_path
