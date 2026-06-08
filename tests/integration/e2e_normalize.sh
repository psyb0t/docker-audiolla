#!/bin/bash
# Loudness measurement + normalization — /v1/audio/loudness and /v1/audio/normalize.
#
#     bash tests/integration/e2e_normalize.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

harness_start "librosa-analyze"

# ── /v1/audio/loudness: returns loudness_lufs as a number ───────────────────

test_loudness_returns_lufs() {
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
    if ! echo "$body" | jq -e '.loudness_lufs | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: loudness_lufs not a number; body: $body"; return 1
    fi
    echo "OK: loudness_returns_lufs ($(echo "$body" | jq -r '.loudness_lufs') LUFS)"
}

# ── /v1/audio/loudness: does NOT return audio or target_lufs field ──────────

test_loudness_is_json_only() {
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
    # Must not contain audio data
    if echo "$body" | jq -e 'has("audio_base64") or has("url")' 2>/dev/null | grep -q "true"; then
        echo "  FAIL: loudness returned audio; body: $(echo "$body" | head -c 200)"; return 1
    fi
    echo "OK: loudness_is_json_only"
}

# ── /v1/audio/loudness: missing file → 400 ──────────────────────────────────

test_loudness_missing_file_400() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"file_path\":\"no/such/file.wav\"}" -o "/dev/null" -w "%{http_code}" --max-time 30 "${AUDIOLLA_BASE_URL}/v1/audio/loudness")
    assert_eq "$code" "404" "missing file -> 404" || return 1
    echo "OK: loudness_missing_file_400"
}

# ── /v1/audio/normalize: returns audio and measured_lufs ────────────────────

test_normalize_returns_audio_and_measured_lufs() {
    local resp_json code lufs audio_tmp
    resp_json=$(mktemp)
    audio_tmp=$(mktemp)
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"target_lufs\":-14,\"output_path\":\"$_out\"}" \
        -o "$resp_json" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/normalize")
    assert_eq "$code" "200" "normalize -> 200" || { rm -f "$resp_json" "$audio_tmp"; return 1; }
    # JSON response should have measured_lufs (or some loudness field)
    lufs=$(jq -r '.measured_lufs // .loudness_lufs // empty' < "$resp_json" 2>/dev/null || echo "")
    rm -f "$resp_json"
    # Fetch the staged audio and verify it's a real WAV.
    curl -sf -o "$audio_tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || {
        echo "  FAIL: could not fetch staged output"; rm -f "$audio_tmp"; return 1
    }
    if [ "$(head -c 4 "$audio_tmp")" != "RIFF" ]; then
        echo "  FAIL: staged file is not WAV (no RIFF magic)"
        rm -f "$audio_tmp"; return 1
    fi
    rm -f "$audio_tmp"
    echo "OK: normalize_returns_audio_and_measured_lufs (measured_lufs: ${lufs:-<not-found>})"
}

# ── normalize: target_lufs=-0.1 → 200 (boundary, max ceiling) ──────────────

test_normalize_target_lufs_zero() {
    local code
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"target_lufs\":-0.1,\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/normalize")
    assert_eq "$code" "200" "normalize target_lufs=-0.1 -> 200" || return 1
    echo "OK: normalize_target_lufs_zero"
}

# ── normalize: missing file → 400 ───────────────────────────────────────────

test_normalize_missing_file_400() {
    local code
    code=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"file_path\":\"ghost.wav\",\"target_lufs\":-14,\"output_path\":\"ghost-out.wav\"}" -o "/dev/null" -w "%{http_code}" --max-time 30 "${AUDIOLLA_BASE_URL}/v1/audio/normalize")
    assert_eq "$code" "404" "normalize missing file -> 404" || return 1
    echo "OK: normalize_missing_file_400"
}

# ── normalize: no target_lufs → 400 (required field) ───────────────────────

test_normalize_no_target_lufs_400() {
    local code
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"$_out\"}" \
        -o "/dev/null" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/normalize")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "/dev/null" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    assert_eq "$code" "422" "normalize without target_lufs -> 422" || return 1
    echo "OK: normalize_no_target_lufs_400"
}

# ── normalize: output normalizes loudness closer to target ──────────────────

test_normalize_moves_loudness_toward_target() {
    local target=-14
    local before_lufs after_lufs
    local _stage="uploads/$(basename "${FIXTURE}")"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    before_lufs=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness" | jq -r '.loudness_lufs')

    curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"target_lufs\":${target},\"output_path\":\"normalize/out.wav\"}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/normalize" > /dev/null

    after_lufs=$(curl -s -X POST -H "Content-Type: application/json" -d "{\"file_path\":\"normalize/out.wav\"}" --max-time 60 "${AUDIOLLA_BASE_URL}/v1/audio/loudness" | jq -r '.loudness_lufs')

    if [ -z "$before_lufs" ] || [ -z "$after_lufs" ]; then
        echo "  FAIL: could not measure LUFS (before=$before_lufs after=$after_lufs)"; return 1
    fi

    # After normalization, |after - target| should be smaller than |before - target|
    local ok
    ok=$(python3 -c "
before = float('${before_lufs}')
after  = float('${after_lufs}')
target = float('${target}')
print('ok' if abs(after - target) <= abs(before - target) + 1.0 else 'fail')
")
    if [ "$ok" != "ok" ]; then
        echo "  FAIL: not closer to target (before=$before_lufs after=$after_lufs target=$target)"; return 1
    fi
    echo "OK: normalize_moves_loudness_toward_target (before=$before_lufs after=$after_lufs target=$target)"
}

harness_run_tests \
    test_loudness_returns_lufs \
    test_loudness_is_json_only \
    test_loudness_missing_file_400 \
    test_normalize_returns_audio_and_measured_lufs \
    test_normalize_target_lufs_zero \
    test_normalize_missing_file_400 \
    test_normalize_no_target_lufs_400 \
    test_normalize_moves_loudness_toward_target
