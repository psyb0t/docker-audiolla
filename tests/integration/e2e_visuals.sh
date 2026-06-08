#!/bin/bash
# Audio visualisations — /v1/audio/visualize/image/{mode} and /v1/audio/visualize/video/{mode}.
# Verifies that the bytes returned are actually valid PNG / MP4 / WebM
# files, not just that the HTTP call succeeded.
#
#     bash tests/integration/e2e_visuals.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "ffmpeg-render"

# PNG magic = 89 50 4E 47 (\x89PNG)
_is_png() {
    head -c 4 "$1" | xxd | tr -d ' \n' | grep -qiE '89504e47'
}

# MP4: bytes 4-8 contain 'ftyp' (ISO base media file type).
_is_mp4() {
    head -c 12 "$1" | tr -d '\0' | grep -q "ftyp"
}

# WebM: starts with EBML magic 1a 45 df a3.
_is_webm() {
    head -c 4 "$1" | xxd | tr -d ' \n' | grep -qiE '1a45dfa3'
}

# ── spectrogram: PNG out ────────────────────────────────────────────────────

test_spectrogram_png() {
    local code tmp
    tmp=$(mktemp --suffix=.png)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":640,\"height\":240,\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/visualize/image/spectrogram")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "visualize/spectrogram -> 200" || { rm -f "$tmp"; return 1; }
    if ! _is_png "$tmp"; then
        echo "  FAIL: response is not a PNG"
        rm -f "$tmp"; return 1
    fi
    local size
    size=$(stat -c%s "$tmp")
    rm -f "$tmp"
    if [ "$size" -lt 500 ]; then
        echo "  FAIL: PNG suspiciously small ($size bytes)"; return 1
    fi
    echo "OK: spectrogram_png ($size bytes)"
}

# ── waveform: PNG out ──────────────────────────────────────────────────────

test_waveform_png() {
    local code tmp
    tmp=$(mktemp --suffix=.png)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":640,\"height\":160,\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/visualize/image/waveform")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "visualize/waveform -> 200" || { rm -f "$tmp"; return 1; }
    if ! _is_png "$tmp"; then
        echo "  FAIL: response is not a PNG"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: waveform_png"
}

# ── spectrogram with output_path: stages PNG in /v1/files ────────────────

test_spectrogram_output_path() {
    local body code fetched
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":320,\"height\":160,\"output_path\":\"viz/spec.png\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/visualize/image/spectrogram")
    if ! echo "$body" | jq -e '.path == "viz/spec.png"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.png)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/viz/spec.png")
    assert_eq "$code" "200" "GET staged PNG -> 200" || { rm -f "$fetched"; return 1; }
    if ! _is_png "$fetched"; then
        echo "  FAIL: staged file not PNG"
        rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: spectrogram_output_path"
}

# ── visualize mode=spectrum: MP4 video out ─────────────────────────────────

test_visualize_spectrum_mp4() {
    local code tmp
    tmp=$(mktemp --suffix=.mp4)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":320,\"height\":180,\"fps\":15,\"container\":\"mp4\",\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/visualize/video/spectrum")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "visualize/spectrum -> 200" || { rm -f "$tmp"; return 1; }
    if ! _is_mp4 "$tmp"; then
        echo "  FAIL: response is not an MP4"
        rm -f "$tmp"; return 1
    fi
    local size
    size=$(stat -c%s "$tmp")
    rm -f "$tmp"
    if [ "$size" -lt 5000 ]; then
        echo "  FAIL: MP4 suspiciously small ($size bytes)"; return 1
    fi
    echo "OK: visualize_spectrum_mp4 ($size bytes)"
}

# ── visualize mode=waves + container=webm ──────────────────────────────────

test_visualize_waves_webm() {
    local code tmp
    tmp=$(mktemp --suffix=.webm)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":320,\"height\":180,\"fps\":15,\"container\":\"webm\",\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/visualize/video/waves")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "visualize/waves webm -> 200" || { rm -f "$tmp"; return 1; }
    if ! _is_webm "$tmp"; then
        echo "  FAIL: response is not a WebM"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: visualize_waves_webm"
}

# ── visualize mode=cqt — exercises a different ffmpeg filter chain ─────────

test_visualize_cqt_mp4() {
    local code tmp
    tmp=$(mktemp --suffix=.mp4)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":320,\"height\":180,\"fps\":15,\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/visualize/video/cqt")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "visualize/cqt -> 200" || { rm -f "$tmp"; return 1; }
    _is_mp4 "$tmp" || { echo "  FAIL: not MP4"; rm -f "$tmp"; return 1; }
    rm -f "$tmp"
    echo "OK: visualize_cqt_mp4"
}

# ── visualize with output_path: stages MP4 in /v1/files ────────────────────

test_visualize_output_path() {
    local body code fetched
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":320,\"height\":180,\"fps\":15,\"output_path\":\"viz/viz.mp4\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/visualize/video/spectrum")
    if ! echo "$body" | jq -e '.path == "viz/viz.mp4"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    fetched=$(mktemp --suffix=.mp4)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/viz/viz.mp4")
    assert_eq "$code" "200" "GET staged MP4 -> 200" || { rm -f "$fetched"; return 1; }
    _is_mp4 "$fetched" || { echo "  FAIL: staged not MP4"; rm -f "$fetched"; return 1; }
    rm -f "$fetched"
    echo "OK: visualize_output_path"
}

# ── unknown visualize mode → 400 ───────────────────────────────────────────

test_visualize_unknown_mode_400() {
    local code body tmp
    tmp=$(mktemp)
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
        "${AUDIOLLA_BASE_URL}/v1/audio/visualize/video/notamode")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    body=$(cat "$tmp")
    rm -f "$tmp"
    assert_eq "$code" "400" "unknown mode -> 400" || return 1
    echo "$body" | grep -qi "mode" || { echo "  FAIL: detail missing 'mode'; body: $body"; return 1; }
    echo "OK: visualize_unknown_mode_400"
}

# ── spectrogram color + scale params ────────────────────────────────────────

test_spectrogram_color_scale() {
    local code tmp
    tmp=$(mktemp --suffix=.png)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":320,\"height\":160,\"color\":\"fire\",\"scale\":\"lin\",\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/visualize/image/spectrogram")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "visualize/spectrogram color=fire scale=lin -> 200" || { rm -f "$tmp"; return 1; }
    if ! _is_png "$tmp"; then
        echo "  FAIL: response is not a PNG"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: spectrogram_color_scale"
}

# ── waveform color param ─────────────────────────────────────────────────────

test_waveform_color() {
    local code tmp
    tmp=$(mktemp --suffix=.png)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"width\":320,\"height\":160,\"color\":\"cyan\",\"output_path\":\"$_out\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/visualize/image/waveform")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "200" "visualize/waveform color=cyan -> 200" || { rm -f "$tmp"; return 1; }
    if ! _is_png "$tmp"; then
        echo "  FAIL: response is not a PNG"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: waveform_color"
}

harness_run_tests \
    test_spectrogram_png \
    test_waveform_png \
    test_spectrogram_output_path \
    test_visualize_spectrum_mp4 \
    test_visualize_waves_webm \
    test_visualize_cqt_mp4 \
    test_visualize_output_path \
    test_visualize_unknown_mode_400 \
    test_spectrogram_color_scale \
    test_waveform_color
