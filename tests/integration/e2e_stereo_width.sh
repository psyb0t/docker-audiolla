#!/bin/bash
# Stereo width — /v1/audio/stereo-width end-to-end.
#
#     bash tests/integration/e2e_stereo_width.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── default width=1.0 → 200 WAV ──────────────────────────────────────────────

test_stereo_width_default() {
    local tmpout code
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    assert_eq "$code" "200" "stereo-width default -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: response is not WAV"
        rm -f "$tmpout"; return 1
    fi
    echo "OK: stereo_width_default ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── width=0.0 (mono) → stereo output with both channels ──────────────────────

test_stereo_width_mono_collapse() {
    local tmpout body ch
    tmpout=$(mktemp --suffix=.wav)
    curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "width=0.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width" > "$tmpout"
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${tmpout}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/info")
    rm -f "$tmpout"
    ch=$(echo "$body" | jq -r '.channels')
    # stereo_width always outputs stereo (via aformat=stereo in the pan filter)
    assert_eq "$ch" "2" "width=0.0 output channels=2" || return 1
    echo "OK: stereo_width_mono_collapse (channels=${ch})"
}

# ── width=2.0 (wide) accepted ─────────────────────────────────────────────────

test_stereo_width_wide() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "width=2.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    assert_eq "$code" "200" "width=2.0 -> 200" || return 1
    echo "OK: stereo_width_wide"
}

# ── output_format=mp3 ─────────────────────────────────────────────────────────

test_stereo_width_output_format_mp3() {
    local code tmpout
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "width=1.0" \
        -F "output_format=mp3" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    assert_eq "$code" "200" "stereo-width mp3 -> 200" || { rm -f "$tmpout"; return 1; }
    if [ ! -s "$tmpout" ]; then
        echo "  FAIL: empty mp3"; rm -f "$tmpout"; return 1
    fi
    echo "OK: stereo_width_output_format_mp3 ($(stat -c%s "$tmpout") bytes)"
    rm -f "$tmpout"
}

# ── width out of range → 400 ──────────────────────────────────────────────────

test_stereo_width_out_of_range_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "width=5.0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    assert_eq "$code" "400" "width=5.0 -> 400" || return 1
    echo "OK: stereo_width_out_of_range_400"
}

# ── negative width → 400 ─────────────────────────────────────────────────────

test_stereo_width_negative_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "width=-0.5" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    assert_eq "$code" "400" "width=-0.5 -> 400" || return 1
    echo "OK: stereo_width_negative_400"
}

# ── missing file → 400 ───────────────────────────────────────────────────────

test_stereo_width_missing_file_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: stereo_width_missing_file_404"
}

# ── output_path staging ───────────────────────────────────────────────────────

test_stereo_width_output_path() {
    local body code tmpout
    body=$(curl -s --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "width=1.5" \
        -F "output_path=stereo/wide.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/stereo-width")
    if ! echo "$body" | jq -e '.path == "stereo/wide.wav"' >/dev/null 2>&1; then
        echo "  FAIL: response missing path; body: $body"; return 1
    fi
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/stereo/wide.wav")
    assert_eq "$code" "200" "GET staged stereo-width -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: staged file is not WAV"; rm -f "$tmpout"; return 1
    fi
    rm -f "$tmpout"
    echo "OK: stereo_width_output_path"
}

harness_run_tests \
    test_stereo_width_default \
    test_stereo_width_mono_collapse \
    test_stereo_width_wide \
    test_stereo_width_output_format_mp3 \
    test_stereo_width_out_of_range_400 \
    test_stereo_width_negative_400 \
    test_stereo_width_missing_file_404 \
    test_stereo_width_output_path
