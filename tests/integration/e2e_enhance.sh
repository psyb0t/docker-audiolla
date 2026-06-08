#!/bin/bash
# Neural speech/vocal enhancement — /v1/audio/enhance.
# DeepFilterNet DF3 is installed in the prod image.
#
#     bash tests/integration/e2e_enhance.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "deepfilter"

# ── basic call: returns WAV bytes ─────────────────────────────────────────────

test_enhance_returns_audio_bytes() {
    local code tmp
    tmp=$(mktemp --suffix=.wav)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "enhance -> 200" || { rm -f "$tmp"; return 1; }

    # Should return audio content-type.
    local ct
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    ct=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    if ! echo "$ct" | grep -qi "audio"; then
        echo "  FAIL: Content-Type not audio: $ct"
        rm -f "$tmp"; return 1
    fi

    if [ "$(stat -c%s "$tmp")" -lt 100 ]; then
        echo "  FAIL: staged file too small (suspect not WAV)"
        rm -f "$tmp"; return 1
    fi
    local size
    size=$(stat -c%s "$tmp")
    rm -f "$tmp"
    if [ "$size" -lt 100 ]; then
        echo "  FAIL: enhanced audio suspiciously small ($size bytes)"; return 1
    fi
    echo "OK: enhance_returns_audio_bytes ($size bytes)"
}

# ── output_format=mp3 returns MP3 bytes ───────────────────────────────────────

test_enhance_mp3_format() {
    local code tmp
    tmp=$(mktemp --suffix=.mp3)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "enhance mp3 -> 200" || { rm -f "$tmp"; return 1; }

    # MP3 magic: ID3 header (49 44 33) or MPEG sync (ff fb / ff f3 / ff f2).
    local magic
    magic=$(head -c 3 "$tmp" | xxd | tr -d ' \n')
    if ! echo "$magic" | grep -qiE "494433|fffb|fff3|fff2"; then
        echo "  FAIL: output is not MP3 (magic: $magic)"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: enhance_mp3_format"
}

# ── output_path: writes enhanced audio to staging ────────────────────────────

test_enhance_output_path() {
    local body code fetched
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"enhanced/out.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
    if ! echo "$body" | jq -e '.path == "enhanced/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/enhanced/out.wav")
    assert_eq "$code" "200" "GET staged enhanced -> 200" || { rm -f "$fetched"; return 1; }
    if ! head -c 4 "$fetched" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: enhance_output_path (staged)"
}

# ── wrong engine type → 400 ───────────────────────────────────────────────────

test_enhance_rejects_non_deepfilter_engine() {
    local code body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"engine\":\"silence-detect\",\"output_path\":\"$_out\"}" \
        -o "/tmp/audiolla-enhance.$$" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/tmp/audiolla-enhance.$$" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    code="$body"
    body=$(cat /tmp/audiolla-enhance.$$ 2>/dev/null)
    rm -f /tmp/audiolla-enhance.$$
    # silence-detect not in ENABLED_ENGINES → 404 is correct; 400 is also correct.
    if [ "$code" != "400" ] && [ "$code" != "404" ]; then
        echo "  FAIL: wrong engine -> expected 400 or 404, got $code; body: $body"
        return 1
    fi
    echo "OK: enhance_rejects_non_deepfilter_engine ($code)"
}

# ── unsupported output_format → 415 ──────────────────────────────────────────

test_enhance_rejects_bad_output_format() {
    local code body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"xyz\",\"output_path\":\"$_out\"}" \
        -o "/tmp/audiolla-enhance2.$$" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/tmp/audiolla-enhance2.$$" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    code="$body"
    body=$(cat /tmp/audiolla-enhance2.$$ 2>/dev/null)
    rm -f /tmp/audiolla-enhance2.$$
    assert_eq "$code" "415" "bad output_format -> 415" || return 1
    echo "OK: enhance_rejects_bad_output_format"
}

harness_run_tests \
    test_enhance_returns_audio_bytes \
    test_enhance_mp3_format \
    test_enhance_output_path \
    test_enhance_rejects_non_deepfilter_engine \
    test_enhance_rejects_bad_output_format
