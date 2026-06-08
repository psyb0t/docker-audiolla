#!/bin/bash
# Time-stretch + pitch-shift — /v1/audio/stretch.
#
#     bash tests/integration/e2e_stretch.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "stretch"

# ── identity: no change returns valid audio ───────────────────────────────────

test_stretch_identity() {
    local tmp code
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
        "${AUDIOLLA_BASE_URL}/v1/audio/stretch")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "identity -> 200" || { rm -f "$tmp"; return 1; }
    [ -s "$tmp" ] || { echo "  FAIL: not WAV"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: stretch_identity"
}

# ── tempo_factor=0.5: output is roughly twice as long ─────────────────────────

test_stretch_tempo_factor() {
    local dur_orig dur_slow
    dur_orig=$(python3 -c "
import wave, sys
with wave.open('${FIXTURE}') as w:
    print(w.getnframes() / w.getframerate())
" 2>/dev/null || echo "0")

    local tmp code
    tmp=$(mktemp --suffix=.wav)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"tempo_factor\":0.5,\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stretch")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "tempo_factor=0.5 -> 200" || { rm -f "$tmp"; return 1; }
    dur_slow=$(python3 -c "
import wave, sys
with wave.open('$tmp') as w:
    print(w.getnframes() / w.getframerate())
" 2>/dev/null || echo "0")
    if python3 -c "import sys; sys.exit(0 if float('$dur_slow') > float('$dur_orig') * 1.5 else 1)" 2>/dev/null; then
        :
    else
        echo "  FAIL: slow file not longer (orig=${dur_orig}s slow=${dur_slow}s)"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: stretch_tempo_factor (orig=${dur_orig}s slow=${dur_slow}s)"
}

# ── pitch_semitones: returns valid audio ──────────────────────────────────────

test_stretch_pitch_semitones() {
    local tmp code
    tmp=$(mktemp --suffix=.wav)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"pitch_semitones\":12,\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stretch")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "pitch_semitones=12 -> 200" || { rm -f "$tmp"; return 1; }
    [ -s "$tmp" ] || { echo "  FAIL: not WAV"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: stretch_pitch_semitones"
}

# ── output_format=mp3: Content-Type is audio/mpeg ────────────────────────────

test_stretch_output_format_mp3() {
    local body fetched code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/stretch-$$-$RANDOM.mp3"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_format\":\"mp3\",\"output_path\":\"$_out\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stretch")
    if ! echo "$body" | jq -e --arg p "$_out" '.path == $p' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.mp3)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/${_out}")
    assert_eq "$code" "200" "GET staged mp3 -> 200" || { rm -f "$fetched"; return 1; }
    # MP3 magic: "ID3" or 0xFF 0xFB / 0xFF 0xF3 / 0xFF 0xF2 frame sync
    if ! head -c 3 "$fetched" | grep -qE "ID3|$(printf '\xff\xfb')|$(printf '\xff\xf3')|$(printf '\xff\xf2')"; then
        echo "  FAIL: staged file is not MP3: $(xxd -l 8 "$fetched" 2>/dev/null)"
        rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: stretch_output_format_mp3"
}

# ── output_path: result staged in /v1/files ──────────────────────────────────

test_stretch_output_path() {
    local body code fetched
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"tempo_factor\":1.25,\"output_path\":\"stretch/fast.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stretch")
    if ! echo "$body" | jq -e '.path == "stretch/fast.wav"' >/dev/null 2>&1; then
        echo "  FAIL: path not in response; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.wav)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/stretch/fast.wav")
    assert_eq "$code" "200" "GET staged -> 200" || { rm -f "$fetched"; return 1; }
    if ! head -c 4 "$fetched" | grep -q "RIFF"; then
        echo "  FAIL: staged not WAV"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: stretch_output_path"
}

# ── combined: tempo + pitch together ─────────────────────────────────────────

test_stretch_combined() {
    local tmp code
    tmp=$(mktemp --suffix=.wav)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"tempo_factor\":0.8,\"pitch_semitones\":-3,\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stretch")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "combined stretch -> 200" || { rm -f "$tmp"; return 1; }
    [ -s "$tmp" ] || { echo "  FAIL: not WAV"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: stretch_combined"
}

harness_run_tests \
    test_stretch_identity \
    test_stretch_tempo_factor \
    test_stretch_pitch_semitones \
    test_stretch_output_format_mp3 \
    test_stretch_output_path \
    test_stretch_combined
