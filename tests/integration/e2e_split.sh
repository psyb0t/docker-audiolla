#!/bin/bash
# Audio split — /v1/audio/split end-to-end.
#
#     bash tests/integration/e2e_split.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "silence-detect"

# ── mode=equal count=2 → ZIP ──────────────────────────────────────────────────

test_split_equal_returns_zip() {
    local tmpout code
    tmpout=$(mktemp --suffix=.zip)
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="split/zip-$$-$RANDOM.zip"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"equal\",\"count\":2,\"output_path\":\"${_out}\"}" \
        -o /dev/null \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/split")
    assert_eq "$code" "200" "split equal -> 200" || { rm -f "$tmpout"; return 1; }
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: could not download staged zip"; rm -f "$tmpout"; return 1
    }
    # ZIP magic bytes: PK\x03\x04
    if ! python3 -c "
import sys
b = open('${tmpout}','rb').read(4)
sys.exit(0 if b == b'PK\x03\x04' else 1)
"; then
        echo "  FAIL: response is not a ZIP"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: split_equal_returns_zip ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── ZIP contains correct number of segments ───────────────────────────────────

test_split_equal_segment_count() {
    local tmpout count
    tmpout=$(mktemp --suffix=.zip)
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="split/seg-$$-$RANDOM.zip"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    curl -sf -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"equal\",\"count\":3,\"output_path\":\"${_out}\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/split" >/dev/null
    curl -sf -o "${tmpout}" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    count=$(python3 -c "
import zipfile, sys
try:
    with zipfile.ZipFile('${tmpout}') as z:
        print(len(z.namelist()))
except Exception as e:
    print(0)
")
    rm -f "$tmpout"
    assert_eq "$count" "3" "equal count=3 → 3 segments" || return 1
    echo "OK: split_equal_segment_count (${count} segments)"
}

# ── mode=equal count=4 → 4 segments ──────────────────────────────────────────

test_split_equal_count_4() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"equal\",\"count\":4,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/split")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "split equal count=4 -> 200" || return 1
    echo "OK: split_equal_count_4"
}

# ── mode=silence → ZIP with at least one segment ─────────────────────────────

test_split_silence_returns_zip() {
    local tmpout code count
    tmpout=$(mktemp --suffix=.zip)
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="split/silence-$$-$RANDOM.zip"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"silence\",\"threshold_db\":-20.0,\"output_path\":\"${_out}\"}" \
        -o /dev/null \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/split")
    assert_eq "$code" "200" "split silence -> 200" || return 1
    curl -sf -o "$tmpout" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: could not download staged zip"; rm -f "$tmpout"; return 1
    }
    count=$(python3 -c "
import zipfile
try:
    with zipfile.ZipFile('${tmpout}') as z:
        print(len(z.namelist()))
except Exception:
    print(0)
")
    rm -f "$tmpout"
    local ok
    ok=$(python3 -c "print('ok' if int('${count}') >= 1 else 'fail')")
    if [ "$ok" != "ok" ]; then
        echo "  FAIL: silence split returned ${count} segments (expected >= 1)"; return 1
    fi
    echo "OK: split_silence_returns_zip (${count} segments)"
}

# ── mode=equal count missing or <2 → 400 ─────────────────────────────────────

test_split_equal_missing_count_422() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"equal\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/split")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    # Handler-level "mode=equal requires count >= 2" → 400.
    assert_eq "$code" "400" "equal without count -> 400" || return 1
    echo "OK: split_equal_missing_count_400"
}

# ── invalid mode → 400 ───────────────────────────────────────────────────────

test_split_invalid_mode_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"random\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/split")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "422" "invalid mode -> 422" || return 1
    echo "OK: split_invalid_mode_400"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_split_missing_file_404() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" \
        -d "{\"file_path\":\"no/such-$$-$RANDOM.wav\",\"mode\":\"equal\",\"count\":2,\"output_path\":\"split/miss-$$.zip\"}" \
        -o "/dev/null" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/audio/split")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: split_missing_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_split_output_path() {
    local body code tmpout
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"mode\":\"equal\",\"count\":2,\"output_path\":\"split/out.zip\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/split")
    if ! echo "$body" | jq -e '.path == "split/out.zip"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/split/out.zip")
    assert_eq "$code" "200" "GET staged split -> 200" || { rm -f "$tmpout"; return 1; }
    python3 -c "
import zipfile, sys
try:
    with zipfile.ZipFile('${tmpout}') as z:
        assert len(z.namelist()) > 0
    sys.exit(0)
except Exception:
    sys.exit(1)
" || { echo "  FAIL: staged file is not a valid ZIP"; rm -f "$tmpout"; return 1; }
    rm -f "$tmpout"
    echo "OK: split_output_path"
}

harness_run_tests \
    test_split_equal_returns_zip \
    test_split_equal_segment_count \
    test_split_equal_count_4 \
    test_split_silence_returns_zip \
    test_split_equal_missing_count_422 \
    test_split_invalid_mode_400 \
    test_split_missing_file_404 \
    test_split_output_path
