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
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
    assert_eq "$code" "200" "enhance -> 200" || { rm -f "$tmp"; return 1; }

    # Should return audio content-type.
    local ct
    ct=$(curl -s -o /dev/null -w "%{content_type}" --max-time 120 \
        -X POST -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
    if ! echo "$ct" | grep -qi "audio"; then
        echo "  FAIL: Content-Type not audio: $ct"
        rm -f "$tmp"; return 1
    fi

    if ! head -c 4 "$tmp" | grep -q "RIFF"; then
        echo "  FAIL: response is not a WAV file"
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
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
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
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_path=enhanced/out.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
    if ! echo "$body" | jq -e '.path == "enhanced/out.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/enhanced/out.wav")
    assert_eq "$code" "200" "GET staged enhanced -> 200" || { rm -f "$fetched"; return 1; }
    if ! head -c 4 "$fetched" | grep -q "RIFF"; then
        echo "  FAIL: staged file not WAV"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: enhance_output_path (staged)"
}

# ── wrong engine type → 400 ───────────────────────────────────────────────────

test_enhance_rejects_non_deepfilter_engine() {
    local code body
    body=$(curl -s -o /tmp/audiolla-enhance.$$ -w "%{http_code}" \
        --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=silence-detect" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
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
    body=$(curl -s -o /tmp/audiolla-enhance2.$$ -w "%{http_code}" \
        --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "output_format=xyz" \
        "${AUDIOLLA_BASE_URL}/v1/audio/enhance")
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
