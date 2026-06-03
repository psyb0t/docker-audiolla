#!/bin/bash
# Audio loop — /v1/audio/loop end-to-end.
#
#     bash tests/integration/e2e_loop.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── count=2 → 200 WAV ─────────────────────────────────────────────────────────

test_loop_returns_wav() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "count=2" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop")
    assert_eq "$code" "200" "loop -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: loop_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── output is longer than source (roughly 2x for count=2) ────────────────────

test_loop_output_longer() {
    local src_dur loop_dur tmpout
    src_dur=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')

    tmpout=$(mktemp --suffix=.wav)
    curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "count=2" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop" > "$tmpout"
    loop_dur=$(curl -s --max-time 60 -X POST \
        -F "file=@${tmpout}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')
    rm -f "$tmpout"

    local ok
    ok=$(python3 -c "
src  = float('${src_dur}')
loop = float('${loop_dur}')
print('ok' if loop > src * 1.5 else 'fail (src={:.2f} loop={:.2f})'.format(src, loop))
")
    if [ "$ok" != "ok" ]; then
        echo "  FAIL: $ok"; return 1
    fi
    echo "OK: loop_output_longer (src=${src_dur}s → loop=${loop_dur}s)"
}

# ── count=3 → output roughly 3x length ───────────────────────────────────────

test_loop_count_3() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "count=3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop")
    assert_eq "$code" "200" "loop count=3 -> 200" || return 1
    echo "OK: loop_count_3"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_loop_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "count=2" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop")
    assert_eq "$code" "200" "loop mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: loop_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── count=1 → 400 ─────────────────────────────────────────────────────────────

test_loop_count_1_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "count=1" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop")
    assert_eq "$code" "400" "count=1 -> 400" || return 1
    echo "OK: loop_count_1_400"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_loop_missing_file_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        -F "count=2" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop")
    assert_eq "$code" "400" "missing file -> 400" || return 1
    echo "OK: loop_missing_file_400"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_loop_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "count=2" \
        -F "output_path=loop/out.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loop")
    if ! echo "$body" | jq -e '.path == "loop/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/loop/out.wav")
    assert_eq "$code" "200" "GET staged loop -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: loop_output_path"
}

harness_run_tests \
    test_loop_returns_wav \
    test_loop_output_longer \
    test_loop_count_3 \
    test_loop_output_format_mp3 \
    test_loop_count_1_400 \
    test_loop_missing_file_400 \
    test_loop_output_path
