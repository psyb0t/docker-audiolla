#!/bin/bash
# Audio reverse — /v1/audio/reverse end-to-end.
#
#     bash tests/integration/e2e_reverse.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── returns WAV ───────────────────────────────────────────────────────────────

test_reverse_returns_wav() {
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
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "reverse -> 200" || { rm -f "$tmpout"; return 1; }
    if [ "$(stat -c%s "$tmpout")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: reverse_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── duration preserved ────────────────────────────────────────────────────────

test_reverse_preserves_duration() {
    local src_dur rev_dur
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    src_dur=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')

    local _out="out/reverse-$$-$RANDOM.wav"
    curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse" >/dev/null
    rev_dur=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')

    local ok
    ok=$(python3 -c "
src = float('${src_dur}')
rev = float('${rev_dur}')
print('ok' if abs(src - rev) <= 0.5 else 'fail (src={:.2f} rev={:.2f})'.format(src, rev))
")
    if [ "$ok" != "ok" ]; then
        echo "  FAIL: $ok"; return 1
    fi
    echo "OK: reverse_preserves_duration (src=${src_dur}s → rev=${rev_dur}s)"
}

# ── double-reverse restores WAV ────────────────────────────────────────────────

test_reverse_double_roundtrip() {
    local tmp1 tmp2 code
    tmp1=$(mktemp --suffix=.wav)
    tmp2=$(mktemp --suffix=.wav)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "$tmp1" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp1" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "first reverse -> 200" || { rm -f "$tmp1" "$tmp2"; return 1; }
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${tmp1}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${tmp1}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "$tmp2" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp2" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    rm -f "$tmp1"
    assert_eq "$code" "200" "second reverse -> 200" || { rm -f "$tmp2"; return 1; }
    if [ "$(stat -c%s "$tmp2")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"; rm -f "$tmp2"; return 1
    fi
    rm -f "$tmp2"
    echo "OK: reverse_double_roundtrip"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_reverse_output_format_mp3() {
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
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "reverse mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: reverse_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_reverse_missing_file_404() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"no/such.wav\",\"output_path\":\"out/missing-$$.wav\"}" \
        -o "/dev/null" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: reverse_missing_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_reverse_output_path() {
    local body code tmpout
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"reverse/out.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse")
    if ! echo "$body" | jq -e '.path == "reverse/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/reverse/out.wav")
    assert_eq "$code" "200" "GET staged reverse -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: reverse_output_path"
}

harness_run_tests \
    test_reverse_returns_wav \
    test_reverse_preserves_duration \
    test_reverse_double_roundtrip \
    test_reverse_output_format_mp3 \
    test_reverse_missing_file_404 \
    test_reverse_output_path
