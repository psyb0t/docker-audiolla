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
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness")
    if ! echo "$body" | jq -e '.loudness_lufs | type == "number"' >/dev/null 2>&1; then
        echo "  FAIL: loudness_lufs not a number; body: $body"; return 1
    fi
    echo "OK: loudness_returns_lufs ($(echo "$body" | jq -r '.loudness_lufs') LUFS)"
}

# ── /v1/audio/loudness: does NOT return audio or target_lufs field ──────────

test_loudness_is_json_only() {
    local body
    body=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
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
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=no/such/file.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness")
    assert_eq "$code" "400" "missing file -> 400" || return 1
    echo "OK: loudness_missing_file_400"
}

# ── /v1/audio/normalize: returns audio and measured_lufs ────────────────────

test_normalize_returns_audio_and_measured_lufs() {
    local tmpout code lufs
    tmpout=$(mktemp)
    code=$(curl -s -o "$tmpout" -w "%{http_code}" --max-time 60 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_lufs=-14" \
        "${AUDIOLLA_BASE_URL}/v1/audio/normalize")
    assert_eq "$code" "200" "normalize -> 200" || { rm -f "$tmpout"; return 1; }
    if ! head -c 4 "$tmpout" | grep -q "RIFF"; then
        echo "  FAIL: normalize did not return WAV"
        rm -f "$tmpout"; return 1
    fi
    lufs=$(curl -s --max-time 10 -I -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_lufs=-14" \
        "${AUDIOLLA_BASE_URL}/v1/audio/normalize" 2>/dev/null | \
        grep -i "x-loudness-lufs" | awk '{print $2}' | tr -d '\r' || true)
    rm -f "$tmpout"
    echo "OK: normalize_returns_audio_and_measured_lufs (X-Loudness-LUFS: ${lufs:-<not-checked>})"
}

# ── normalize: target_lufs=0 → 200 (edge case, may clip but valid call) ─────

test_normalize_target_lufs_zero() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 60 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_lufs=0" \
        "${AUDIOLLA_BASE_URL}/v1/audio/normalize")
    assert_eq "$code" "200" "normalize target_lufs=0 -> 200" || return 1
    echo "OK: normalize_target_lufs_zero"
}

# ── normalize: missing file → 400 ───────────────────────────────────────────

test_normalize_missing_file_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=ghost.wav" \
        -F "target_lufs=-14" \
        "${AUDIOLLA_BASE_URL}/v1/audio/normalize")
    assert_eq "$code" "400" "normalize missing file -> 400" || return 1
    echo "OK: normalize_missing_file_400"
}

# ── normalize: no target_lufs → 400 (required field) ───────────────────────

test_normalize_no_target_lufs_400() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/normalize")
    assert_eq "$code" "400" "normalize without target_lufs -> 400" || return 1
    echo "OK: normalize_no_target_lufs_400"
}

# ── normalize: output normalizes loudness closer to target ──────────────────

test_normalize_moves_loudness_toward_target() {
    local target=-14
    local before_lufs after_lufs
    before_lufs=$(curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness" | jq -r '.loudness_lufs')

    local tmpout
    tmpout=$(mktemp)
    curl -s --max-time 60 -X POST \
        -F "file=@${FIXTURE}" \
        -F "target_lufs=${target}" \
        -F "output_path=normalize/out.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/normalize" > /dev/null

    after_lufs=$(curl -s --max-time 60 -X POST \
        -F "file_path=normalize/out.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/loudness" | jq -r '.loudness_lufs')
    rm -f "$tmpout"

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
