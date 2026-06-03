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
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "speed=2.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    assert_eq "$code" "200" "speed -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: speed_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── 2x speed produces roughly half-duration output ───────────────────────────

test_speed_double_halves_duration() {
    local src_dur speed_dur tmpout
    src_dur=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')

    tmpout=$(mktemp --suffix=.wav)
    curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "speed=2.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed" > "$tmpout"
    speed_dur=$(curl -s --max-time 60 -X POST \
        -F "file=@${tmpout}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')
    rm -f "$tmpout"

    local ok
    ok=$(python3 -c "
src   = float('${src_dur}')
fast  = float('${speed_dur}')
# allow 20% slop for encoder padding
expected = src / 2.0
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
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "speed=0.5" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    assert_eq "$code" "200" "speed=0.5 -> 200" || return 1
    echo "OK: speed_half"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_speed_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "speed=1.5" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
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
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "speed=20.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    assert_eq "$code" "400" "speed=20.0 -> 400" || return 1
    echo "OK: speed_out_of_range_400"
}

# ── speed missing → 422 ───────────────────────────────────────────────────────

test_speed_missing_speed_422() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    assert_eq "$code" "422" "missing speed -> 422" || return 1
    echo "OK: speed_missing_speed_422"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_speed_missing_file_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        -F "speed=2.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/speed")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: speed_missing_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_speed_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "speed=1.5" \
        -F "output_path=speed/fast.wav" \
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
