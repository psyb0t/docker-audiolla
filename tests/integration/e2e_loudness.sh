#!/bin/bash
# pyloudnorm LUFS analyze + normalize end-to-end. CPU-only.
#
# Fixture: tests/integration/.fixtures/audio.wav.
#
#     bash tests/integration/e2e_loudness.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

_skip_if_no_fixture() {
    if [ ! -f "$FIXTURE" ]; then
        echo "  SKIP: fixture not found at ${FIXTURE}"
        return 0
    fi
    return 1
}

# ── Analyze-only: no target_lufs → JSON with measured LUFS ───────────────────

test_loudness_analyze_only() {
    _skip_if_no_fixture && return 0
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness")
    if ! echo "$body" | jq -e '.loudness_lufs != null' >/dev/null 2>&1; then
        echo "  FAIL: response missing loudness_lufs"
        echo "  body: $body"
        return 1
    fi
    local normalized
    normalized=$(echo "$body" | jq -r '.normalized')
    assert_eq "$normalized" "false" "analyze-only normalized=false" || return 1

    local lufs
    lufs=$(echo "$body" | jq -r '.loudness_lufs')
    if ! awk -v l="$lufs" 'BEGIN{exit (l>=-70 && l<=0) ? 0 : 1}'; then
        echo "  FAIL: lufs $lufs outside [-70,0]"; return 1
    fi
    echo "OK: loudness_analyze_only (${lufs} LUFS)"
}

# ── Normalize: target_lufs set → audio bytes with measured LUFS in headers ───

test_loudness_normalize_to_minus14() {
    _skip_if_no_fixture && return 0
    local resp code target=-14
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/loudnorm-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    # v1.0.0: normalize returns JSON {path, size, measured_lufs?, ...} when
    # output_path is set. No more X-Loudness-LUFS / X-Target-LUFS headers.
    resp=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"target_lufs\":${target},\"output_format\":\"wav\",\"output_path\":\"$_out\"}" \
        --max-time 120 \
        "${AUDIOLLA_BASE_URL}/v1/audio/normalize")
    if ! echo "$resp" | jq -e '.path' >/dev/null 2>&1; then
        echo "  FAIL: normalize response missing .path; body: $resp"; return 1
    fi
    # Fetch the staged output and verify RIFF magic.
    local fetched
    fetched=$(mktemp)
    curl -sf -o "$fetched" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: GET staged normalized failed"; rm -f "$fetched"; return 1
    }
    if [ "$(head -c 4 "$fetched")" != "RIFF" ]; then
        echo "  FAIL: normalized file is not WAV (no RIFF)"; rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"

    # Round-trip through /v1/audio/loudness to confirm we hit the target.
    local roundtrip post_lufs
    roundtrip=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_out\"}" \
        --max-time 60 \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness")
    post_lufs=$(echo "$roundtrip" | jq -r '.loudness_lufs')
    if [ -z "$post_lufs" ] || [ "$post_lufs" = "null" ]; then
        echo "  FAIL: post-normalize roundtrip returned no LUFS; body: $roundtrip"
        return 1
    fi
    if ! awk -v p="$post_lufs" -v t="$target" \
        'BEGIN{d=p-t; if(d<0) d=-d; exit (d<=0.5) ? 0 : 1}'; then
        echo "  FAIL: normalized output LUFS ${post_lufs} not within 0.5 dB of target ${target}"
        return 1
    fi
    echo "OK: loudness_normalize_to_minus14 (measured_out=${post_lufs} target=${target})"
}

# ── Non-audio input → 400 ────────────────────────────────────────────────────

test_loudness_bad_input_400() {
    local tmp code
    tmp=$(mktemp -t junk.XXXXXX) || return 2
    echo "not audio" > "$tmp"
    # shellcheck disable=SC2064
    trap "rm -f '$tmp'" RETURN
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${tmp}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${tmp}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "400" "non-audio -> 400" || return 1
    echo "OK: loudness_bad_input_400"
}

harness_run_tests \
    test_loudness_analyze_only \
    test_loudness_normalize_to_minus14 \
    test_loudness_bad_input_400
