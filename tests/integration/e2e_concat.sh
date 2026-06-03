#!/bin/bash
# Audio concat — /v1/audio/concat end-to-end.
#
#     bash tests/integration/e2e_concat.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

_stage_fixtures() {
    curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "start_sec=0.0" -F "end_sec=3.0" \
        -F "output_path=concat/part_a.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim" > /dev/null || return 1
    curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "start_sec=3.0" -F "end_sec=6.0" \
        -F "output_path=concat/part_b.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim" > /dev/null || return 1
}

harness_start "librosa-analyze"
_stage_fixtures || { echo "FATAL: fixture staging failed" >&2; exit 1; }

FILES_JSON='[{"file_path":"concat/part_a.wav"},{"file_path":"concat/part_b.wav"}]'

# ── two parts → 200 WAV ───────────────────────────────────────────────────────

test_concat_returns_wav() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "files=${FILES_JSON}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    assert_eq "$code" "200" "concat -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: concat_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── output is longer than a single part ──────────────────────────────────────

test_concat_output_longer_than_part() {
    local part_dur concat_dur tmpout
    part_dur=$(curl -s --max-time 60 -X POST \
        -F "file_path=concat/part_a.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')

    tmpout=$(mktemp --suffix=.wav)
    curl -s --max-time 120 -X POST \
        -F "files=${FILES_JSON}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat" > "$tmpout"
    concat_dur=$(curl -s --max-time 60 -X POST \
        -F "file=@${tmpout}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec')
    rm -f "$tmpout"

    local ok
    ok=$(python3 -c "
part  = float('${part_dur}')
total = float('${concat_dur}')
print('ok' if total > part else 'fail (part={} concat={})'.format(part, total))
")
    if [ "$ok" != "ok" ]; then
        echo "  FAIL: $ok"; return 1
    fi
    echo "OK: concat_output_longer_than_part (part=${part_dur}s → concat=${concat_dur}s)"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_concat_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "files=${FILES_JSON}" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    assert_eq "$code" "200" "concat mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: concat_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── only one file → 400 ───────────────────────────────────────────────────────

test_concat_one_file_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F 'files=[{"file_path":"concat/part_a.wav"}]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    assert_eq "$code" "400" "one file -> 400" || return 1
    echo "OK: concat_one_file_400"
}

# ── invalid JSON files → 400 ──────────────────────────────────────────────────

test_concat_invalid_files_json_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "files=not-json" \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    assert_eq "$code" "400" "invalid JSON -> 400" || return 1
    echo "OK: concat_invalid_files_json_400"
}

# ── missing files param → 422 ─────────────────────────────────────────────────

test_concat_missing_files_422() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    assert_eq "$code" "422" "missing files -> 422" || return 1
    echo "OK: concat_missing_files_422"
}

# ── nonexistent file in array → 400 ──────────────────────────────────────────

test_concat_missing_file_in_array_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F 'files=[{"file_path":"concat/part_a.wav"},{"file_path":"concat/ghost.wav"}]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    assert_eq "$code" "400" "missing file in array -> 400" || return 1
    echo "OK: concat_missing_file_in_array_400"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_concat_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "files=${FILES_JSON}" \
        -F "output_path=concat/joined.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    if ! echo "$body" | jq -e '.path == "concat/joined.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/concat/joined.wav")
    assert_eq "$code" "200" "GET staged concat -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: concat_output_path"
}

harness_run_tests \
    test_concat_returns_wav \
    test_concat_output_longer_than_part \
    test_concat_output_format_mp3 \
    test_concat_one_file_400 \
    test_concat_invalid_files_json_400 \
    test_concat_missing_files_422 \
    test_concat_missing_file_in_array_400 \
    test_concat_output_path
