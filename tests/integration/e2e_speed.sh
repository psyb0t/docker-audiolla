#!/bin/bash
# Audio speed — /v1/audio/speed end-to-end.
#
#     bash tests/integration/e2e_speed.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── returns WAV ───────────────────────────────────────────────────────────────

test_speed_returns_wav() {
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
        -d "{\"file_path\":\"$_stage\",\"speed\":2.0,\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "speed -> 200" || { rm -f "$tmpout"; return 1; }
    if [ "$(stat -c%s "$tmpout")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: speed_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── 2x speed produces roughly half-duration output ───────────────────────────

test_speed_double_halves_duration() {
    local src_dur speed_dur
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    src_dur=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')

    local _out="out/speed-$$-$RANDOM.wav"
    curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"speed\":2.0,\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed" >/dev/null
    speed_dur=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')

    local ok
    ok=$(python3 -c "
src   = float('${src_dur}')
fast  = float('${speed_dur}')
print('ok' if fast < src * 0.75 else 'fail (src={:.2f} speed2x={:.2f})'.format(src, fast))
")
    if [ "$ok" != "ok" ]; then
        echo "  FAIL: $ok"; return 1
    fi
    echo "OK: speed_double_halves_duration (src=${src_dur}s → 2x=${speed_dur}s)"
}

# ── speed=0.5 accepted ────────────────────────────────────────────────────────

test_speed_half() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"speed\":0.5,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "speed=0.5 -> 200" || return 1
    echo "OK: speed_half"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_speed_output_format_mp3() {
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
        -d "{\"file_path\":\"$_stage\",\"speed\":1.5,\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$tmpout" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "speed mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: speed_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── speed out of range → 400 ─────────────────────────────────────────────────

test_speed_out_of_range_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"speed\":20.0,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    [[ "$code" = "400" || "$code" = "422" ]] && echo "  OK: $speed=20.0 -> 422 (code=$code)" || { echo "  FAIL: $speed=20.0 -> 422 expected 400 or 422, got $code"; return 1; } || return 1
    echo "OK: speed_out_of_range_400"
}

# ── speed missing → 422 ───────────────────────────────────────────────────────

test_speed_missing_speed_422() {
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
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "422" "missing speed -> 422" || return 1
    echo "OK: speed_missing_speed_422"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_speed_missing_file_404() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"no/such.wav\",\"speed\":2.0,\"output_path\":\"out/missing-$$.wav\"}" \
        -o "/dev/null" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: speed_missing_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_speed_output_path() {
    local body code tmpout
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"speed\":1.5,\"output_path\":\"speed/fast.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    if ! echo "$body" | jq -e '.path == "speed/fast.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/speed/fast.wav")
    assert_eq "$code" "200" "GET staged speed -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: speed_output_path"
}

harness_run_tests \
    test_speed_returns_wav \
    test_speed_double_halves_duration \
    test_speed_half \
    test_speed_output_format_mp3 \
    test_speed_out_of_range_400 \
    test_speed_missing_speed_422 \
    test_speed_missing_file_404 \
    test_speed_output_path
