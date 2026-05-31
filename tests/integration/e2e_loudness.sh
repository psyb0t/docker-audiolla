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
    body=$(curl -s --max-time 60 -X POST -F "file=@${FIXTURE}" \
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
    local tmp headers code
    tmp=$(mktemp -t audiolla-norm.XXXXXX) || return 2
    headers=$(mktemp -t audiolla-norm-h.XXXXXX) || return 2
    # shellcheck disable=SC2064
    trap "rm -f '$tmp' '$headers'" RETURN
    code=$(curl -s -o "$tmp" -D "$headers" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_lufs=-14" \
        -F "output_format=wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness")
    assert_eq "$code" "200" "normalize -> 200" || return 1
    local head4
    head4=$(head -c 4 "$tmp" | od -An -c | tr -d ' \n')
    assert_eq "$head4" "RIFF" "normalized → RIFF" || return 1

    # Server should set X-Loudness-LUFS + X-Target-LUFS response headers.
    local measured target
    measured=$(grep -i '^x-loudness-lufs:' "$headers" | tr -d '\r' | awk '{print $2}')
    target=$(grep -i '^x-target-lufs:' "$headers" | tr -d '\r' | awk '{print $2}')
    if [ -z "$measured" ] || [ -z "$target" ]; then
        echo "  FAIL: missing X-Loudness-LUFS / X-Target-LUFS headers"
        return 1
    fi
    assert_eq "$target" "-14.0" "echoed target_lufs = -14.0" || return 1

    # Verify the NORMALIZED output is actually at the target LUFS — POST the
    # output back through /v1/audio/loudness (analyze-only) and assert the
    # measured value lies within 0.5 dB of the target (phase doc §1.7 gate).
    local roundtrip post_lufs delta
    roundtrip=$(curl -s --max-time 60 -X POST -F "file=@${tmp}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness")
    post_lufs=$(echo "$roundtrip" | jq -r '.loudness_lufs')
    if [ -z "$post_lufs" ] || [ "$post_lufs" = "null" ]; then
        echo "  FAIL: post-normalize roundtrip returned no LUFS"
        echo "  body: $roundtrip"
        return 1
    fi
    # awk-based abs-difference check: |post_lufs - target_lufs| <= 0.5
    if ! awk -v p="$post_lufs" -v t="$target" \
        'BEGIN{d=p-t; if(d<0) d=-d; exit (d<=0.5) ? 0 : 1}'; then
        echo "  FAIL: normalized output LUFS ${post_lufs} not within 0.5 dB of target ${target}"
        return 1
    fi
    echo "OK: loudness_normalize_to_minus14 (measured_in=${measured} measured_out=${post_lufs} target=${target})"
}

# ── Non-audio input → 400 ────────────────────────────────────────────────────

test_loudness_bad_input_400() {
    local tmp code
    tmp=$(mktemp -t junk.XXXXXX) || return 2
    echo "not audio" > "$tmp"
    # shellcheck disable=SC2064
    trap "rm -f '$tmp'" RETURN
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST -F "file=@${tmp}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness")
    assert_eq "$code" "400" "non-audio -> 400" || return 1
    echo "OK: loudness_bad_input_400"
}

harness_run_tests \
    test_loudness_analyze_only \
    test_loudness_normalize_to_minus14 \
    test_loudness_bad_input_400
