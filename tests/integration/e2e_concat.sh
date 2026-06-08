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
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"start_sec\":0.0,\"end_sec\":3.0,\"output_path\":\"concat/part_a.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim"
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"start_sec\":3.0,\"end_sec\":6.0,\"output_path\":\"concat/part_b.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/trim"
}

harness_start "librosa-analyze"
_stage_fixtures || { echo "FATAL: fixture staging failed" >&2; exit 1; }

FILES_JSON='[{"file_path":"concat/part_a.wav"},{"file_path":"concat/part_b.wav"}]'

# ── two parts → 200 WAV ───────────────────────────────────────────────────────

test_concat_returns_wav() {
    local tmpout code
    tmpout=$(mktemp)
    _fp=$(echo "${FILES_JSON}" | jq -c "[.[].file_path]")
_json="{\"file_paths\":${_fp},\"output_path\":\"out/multi-$$-$RANDOM.wav\"}"
code=$(curl -s -X POST -H "Content-Type: application/json" -d "$_json" -o "$tmpout" -w "%{http_code}" "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    assert_eq "$code" "200" "concat -> 200" || { rm -f "$tmpout"; return 1; }
    if ! jq -e .path $tmpout >/dev/null 2>&1; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: concat_returns_wav ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── output is longer than a single part ──────────────────────────────────────

test_concat_output_longer_than_part() {
    local _out part_dur concat_dur
    _out="concat/joined-len-$$-$RANDOM.wav"
    # Concatenate the two parts to a staged file.
    local _fp
    _fp=$(echo "${FILES_JSON}" | jq -c '[.[].file_path]')
    curl -sf -X POST -H "Content-Type: application/json" \
        -d "{\"file_paths\":${_fp},\"output_path\":\"${_out}\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat" >/dev/null
    # Compare durations.
    part_dur=$(curl -sf -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"concat/part_a.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec // .duration // 0')
    concat_dur=$(curl -sf -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"${_out}\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info" | jq -r '.duration_sec // .duration // 0')
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
    _fp=$(echo "${FILES_JSON}" | jq -c "[.[].file_path]")
_json="{\"file_paths\":${_fp},\"output_format\":\"mp3\",\"output_path\":\"out/multi-$$-$RANDOM.wav\"}"
code=$(curl -s -X POST -H "Content-Type: application/json" -d "$_json" -o "$tmpout" -w "%{http_code}" "${AUDIOLLA_BASE_URL}/v1/audio/concat")
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
    # Handler enforces ≥2 inputs → 400.
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        -d '{"file_paths":["concat/part_a.wav"],"output_path":"concat/single-$$.wav"}' \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    assert_eq "$code" "400" "one file -> 400" || return 1
    echo "OK: concat_one_file_400"
}

# ── invalid JSON files → 400 ──────────────────────────────────────────────────

test_concat_invalid_files_json_400() {
    local code
    # file_paths must be a list of strings — sending a string is wrong type → Pydantic 422.
    code=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"file_paths\":\"not-a-list\"}" -o "/dev/null" -w "%{http_code}" --max-time 30 "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    assert_eq "$code" "422" "invalid file_paths type -> 422" || return 1
    echo "OK: concat_invalid_files_json_400"
}

# ── missing files param → 422 ─────────────────────────────────────────────────

test_concat_missing_files_422() {
    local code
    # Empty body — neither file_paths nor file_urls provided → handler-level 400 (XOR check).
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        -d '{}' \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    assert_eq "$code" "400" "no inputs -> 400" || return 1
    echo "OK: concat_missing_files_422"
}

# ── nonexistent file in array → 400 ──────────────────────────────────────────

test_concat_missing_file_in_array_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST -H "Content-Type: application/json" \
        -d '{"file_paths":["concat/part_a.wav","concat/ghost-missing.wav"],"output_path":"concat/404-$$.wav"}' \
        "${AUDIOLLA_BASE_URL}/v1/audio/concat")
    assert_eq "$code" "404" "missing file in array -> 404" || return 1
    echo "OK: concat_missing_file_in_array_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_concat_output_path() {
    local body code tmpout
    _fp=$(echo "${FILES_JSON}" | jq -c "[.[].file_path]")
_json="{\"file_paths\":${_fp},\"output_path\":\"concat/joined.wav\"}"
body=$(curl -s -X POST -H "Content-Type: application/json" -d "$_json" "${AUDIOLLA_BASE_URL}/v1/audio/concat")
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
    test_concat_missing_file_in_array_404 \
    test_concat_output_path
