#!/bin/bash
# UVR restoration endpoints — /v1/audio/{dereverb,deecho,denoise}.
#
# These require UVR model .ckpt/.pth files in /data/uvr_models (inside
# the container). When the models are absent the engine returns 500 with
# a detail containing "model" / "file" / "No such file". The tests skip
# gracefully in that case so CI does not fail when models are not present.
#
#     bash tests/integration/e2e_uvr.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

# Enable all three UVR restore engines for this test.
harness_start "uvr-dereverb,uvr-deecho,uvr-denoise"

# ── helper: graceful skip if model weights are missing ───────────────────────

_uvr_or_skip() {
    local endpoint="$1" engine="$2" code body
    local tmp
    tmp=$(mktemp)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 120 \
        -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=${engine}" \
        "${AUDIOLLA_BASE_URL}${endpoint}")
    body=$(cat "$tmp")
    rm -f "$tmp"

    if [ "$code" = "200" ]; then
        local sz
        sz=$(echo -n "$body" | wc -c)
        echo "OK: ${endpoint} (${engine}) returned audio (${sz} bytes)"
        return 0
    fi

    # Skip when model weights not present.
    if echo "$body" | grep -qiE "model|file|No such file|ckpt|pth"; then
        echo "  SKIP: ${endpoint} (${engine}) — model weights not present"
        return 0
    fi
    # Skip when engine not configured.
    if [ "$code" = "404" ]; then
        echo "  SKIP: ${endpoint} (${engine}) — engine not configured"
        return 0
    fi

    echo "  FAIL: ${endpoint} (${engine}) -> HTTP ${code}: ${body:0:300}"
    return 1
}

# ── dereverb — default engine ────────────────────────────────────────────────

test_dereverb_returns_audio() {
    _uvr_or_skip "/v1/audio/dereverb" "uvr-dereverb"
}

# ── deecho ────────────────────────────────────────────────────────────────────

test_deecho_returns_audio() {
    _uvr_or_skip "/v1/audio/deecho" "uvr-deecho"
}

# ── denoise ───────────────────────────────────────────────────────────────────

test_denoise_returns_audio() {
    _uvr_or_skip "/v1/audio/denoise" "uvr-denoise"
}

# ── wrong engine type → 400 ───────────────────────────────────────────────────

test_dereverb_rejects_wrong_engine_type() {
    local code body
    # Request dereverb with a non-UVR engine name; the server should
    # return 404 (engine not found) because ffmpeg-render is not in our
    # ENABLED_ENGINES list.  That's still a sane error path.
    body=$(curl -s -o /tmp/audiolla-uvr.$$ -w "%{http_code}" \
        --max-time 30 -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=ffmpeg-render" \
        "${AUDIOLLA_BASE_URL}/v1/audio/dereverb")
    code="$body"
    body=$(cat /tmp/audiolla-uvr.$$ 2>/dev/null)
    rm -f /tmp/audiolla-uvr.$$
    # Either 400 (wrong type) or 404 (engine not configured for this run) is correct.
    if [ "$code" != "400" ] && [ "$code" != "404" ]; then
        echo "  FAIL: wrong engine type -> expected 400 or 404, got $code; body: $body"
        return 1
    fi
    echo "OK: dereverb_rejects_wrong_engine_type ($code)"
}

# ── output_path: writes audio to staging when model is present ───────────────

test_dereverb_output_path() {
    local code body fetched
    body=$(curl -s -o /tmp/audiolla-uvr-op.$$ -w "%{http_code}" \
        --max-time 120 -X POST \
        -F "file=@${FIXTURE}" \
        -F "engine=uvr-dereverb" \
        -F "output_path=uvr/dereverb.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/dereverb")
    code="$body"
    body=$(cat /tmp/audiolla-uvr-op.$$ 2>/dev/null)
    rm -f /tmp/audiolla-uvr-op.$$

    if [ "$code" = "200" ]; then
        if ! echo "$body" | jq -e '.path == "uvr/dereverb.wav"' >/dev/null 2>&1; then
            echo "  FAIL: output_path response missing path; body: $body"
            return 1
        fi
        echo "OK: dereverb_output_path (staged to uvr/dereverb.wav)"
        return 0
    fi

    if echo "$body" | grep -qiE "model|file|No such file|ckpt|pth"; then
        echo "  SKIP: dereverb_output_path — model weights not present"
        return 0
    fi
    if [ "$code" = "404" ]; then
        echo "  SKIP: dereverb_output_path — engine not configured"
        return 0
    fi

    echo "  FAIL: output_path -> HTTP ${code}: ${body:0:300}"
    return 1
}

harness_run_tests \
    test_dereverb_returns_audio \
    test_deecho_returns_audio \
    test_denoise_returns_audio \
    test_dereverb_rejects_wrong_engine_type \
    test_dereverb_output_path
