#!/bin/bash
# librosa MIR analysis end-to-end. CPU-only.
#
# Fixture: tests/integration/.fixtures/audio.wav.
#
#     bash tests/integration/e2e_analysis.sh

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

# ── /healthz wired ───────────────────────────────────────────────────────────

test_healthz_has_librosa() {
    local out
    out=$(audiolla_get "/healthz") || { echo "  FAIL: /healthz unreachable"; return 1; }
    assert_contains "$out" "librosa-analyze" "/healthz lists librosa-analyze" || return 1
    echo "OK: healthz_has_librosa"
}

# ── Default: all features returned with sane shapes ──────────────────────────

test_analyze_all_features() {
    _skip_if_no_fixture && return 0
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s --max-time 120 -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"features\":[\"bpm\",\"key\",\"loudness\",\"duration\",\"spectral_centroid\",\"rms\",\"zcr\"]}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/analyze")

    for k in duration bpm key loudness_lufs spectral_centroid rms zcr; do
        if ! echo "$body" | jq -e --arg k "$k" '.[$k] != null' >/dev/null 2>&1; then
            echo "  FAIL: response missing or null \"$k\""
            echo "  body: $body"
            return 1
        fi
    done

    local dur
    dur=$(echo "$body" | jq -r '.duration')
    if ! awk -v d="$dur" 'BEGIN{exit (d>=1 && d<=120) ? 0 : 1}'; then
        echo "  FAIL: duration $dur outside sane [1,120] range"; return 1
    fi

    local lufs
    lufs=$(echo "$body" | jq -r '.loudness_lufs')
    if ! awk -v l="$lufs" 'BEGIN{exit (l>=-70 && l<=0) ? 0 : 1}'; then
        echo "  FAIL: loudness $lufs outside sane [-70,0] LUFS range"; return 1
    fi

    echo "OK: analyze_all_features (duration=${dur}s lufs=${lufs})"
}

# ── No features list → returns all features by default ───────────────────────

test_analyze_default_features() {
    _skip_if_no_fixture && return 0
    local body
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    body=$(curl -s --max-time 120 -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/analyze")
    if ! echo "$body" | jq -e '.duration != null' >/dev/null 2>&1; then
        echo "  FAIL: default-features response missing duration"
        echo "  body: $body"
        return 1
    fi
    echo "OK: analyze_default_features"
}

# ── Unknown feature name → 400 ───────────────────────────────────────────────

test_analyze_unknown_feature_400() {
    _skip_if_no_fixture && return 0
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s --max-time 60 -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"features\":[\"not-a-feature\"]}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/analyze")
    assert_eq "$code" "400" "unknown feature -> 400" || return 1
    echo "OK: analyze_unknown_feature_400"
}

# ── Non-audio input → 400 ────────────────────────────────────────────────────

test_analyze_bad_input_400() {
    local tmp code
    tmp=$(mktemp -t junk.XXXXXX) || return 2
    echo "this is not audio" > "$tmp"
    # shellcheck disable=SC2064
    trap "rm -f '$tmp'" RETURN
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${tmp}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${tmp}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s --max-time 60 -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/analyze")
    assert_eq "$code" "400" "non-audio -> 400" || return 1
    echo "OK: analyze_bad_input_400"
}

harness_run_tests \
    test_healthz_has_librosa \
    test_analyze_all_features \
    test_analyze_default_features \
    test_analyze_unknown_feature_400 \
    test_analyze_bad_input_400
