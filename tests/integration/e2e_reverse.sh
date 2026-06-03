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
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse")
    assert_eq "$code" "200" "reverse -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: reverse_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── duration preserved ────────────────────────────────────────────────────────

test_reverse_preserves_duration() {
    local src_dur rev_dur tmpout
    src_dur=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')

    tmpout=$(mktemp --suffix=.wav)
    curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse" > "$tmpout"
    rev_dur=$(curl -s --max-time 60 -X POST \
        -F "file=@${tmpout}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')
    rm -f "$tmpout"

    local ok
    ok=$(python3 -c "
src = float('${src_dur}')
rev = float('${rev_dur}')
# allow 0.1 s rounding slop
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
    code=$(curl -s -o "$tmp1" -w "%{http_code}" --max-time 120 \
        -X POST -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse")
    assert_eq "$code" "200" "first reverse -> 200" || { rm -f "$tmp1" "$tmp2"; return 1; }
    code=$(curl -s -o "$tmp2" -w "%{http_code}" --max-time 120 \
        -X POST -F "file=@${tmp1}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse")
    rm -f "$tmp1"
    assert_eq "$code" "200" "second reverse -> 200" || { rm -f "$tmp2"; return 1; }
    if ! head -c 4 "$tmp2" | grep -q "RIFF"; then
        echo "  FAIL: double-reversed output is not WAV"; rm -f "$tmp2"; return 1
    fi
    rm -f "$tmp2"
    echo "OK: reverse_double_roundtrip"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_reverse_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse")
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
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/reverse")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: reverse_missing_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_reverse_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_path=reverse/out.wav" \
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
