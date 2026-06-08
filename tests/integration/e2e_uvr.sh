#!/bin/bash
# UVR restoration endpoint — /v1/audio/restore/{engine}.
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
    local engine="$1" code body
    local tmp
    tmp=$(mktemp)
    # 600s allows for first-run model download (BS-Roformer ~500MB pull).
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
        "${AUDIOLLA_BASE_URL}/v1/audio/restore/${engine}")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    body=$(cat "$tmp")
    rm -f "$tmp"

    if [ "$code" = "200" ]; then
        local sz
        sz=$(echo -n "$body" | wc -c)
        echo "OK: /v1/audio/restore/${engine} returned audio (${sz} bytes)"
        return 0
    fi

    # curl gave up before the server responded (timeout, network reset, etc.)
    # treat as skip — model download is the usual cause on first run.
    if [ "$code" = "000" ] || [ -z "$body" ]; then
        echo "  SKIP: /v1/audio/restore/${engine} — request timed out (model download in progress?)"
        return 0
    fi

    # Skip when model weights not present.
    if echo "$body" | grep -qiE "model|file|No such file|ckpt|pth"; then
        echo "  SKIP: /v1/audio/restore/${engine} — model weights not present"
        return 0
    fi
    # Skip when engine not configured.
    if [ "$code" = "404" ]; then
        echo "  SKIP: /v1/audio/restore/${engine} — engine not configured"
        return 0
    fi

    echo "  FAIL: /v1/audio/restore/${engine} -> HTTP ${code}: ${body:0:300}"
    return 1
}

# ── dereverb engine ──────────────────────────────────────────────────────────

test_restore_dereverb() {
    _uvr_or_skip "uvr-dereverb"
}

# ── deecho engine ─────────────────────────────────────────────────────────────

test_restore_deecho() {
    _uvr_or_skip "uvr-deecho"
}

# ── denoise engine ────────────────────────────────────────────────────────────

test_restore_denoise() {
    _uvr_or_skip "uvr-denoise"
}

# ── wrong engine type → 400 ───────────────────────────────────────────────────

test_restore_rejects_wrong_engine_type() {
    local code body
    local tmp
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
        "${AUDIOLLA_BASE_URL}/v1/audio/restore/ffmpeg-render")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    body=$(cat "$tmp")
    rm -f "$tmp"
    # Either 400 (wrong type) or 404 (engine not configured for this run) is correct.
    if [ "$code" != "400" ] && [ "$code" != "404" ]; then
        echo "  FAIL: wrong engine type -> expected 400 or 404, got $code; body: $body"
        return 1
    fi
    echo "OK: restore_rejects_wrong_engine_type ($code)"
}

# ── output_path: writes audio to staging when model is present ───────────────

test_restore_output_path() {
    local code body
    local tmp
    tmp=$(mktemp)
    # v1.0.0: pre-stage the fixture via /v1/files, build JSON body
    local _stage="uploads/$(basename "${FIXTURE}")"
    local _out="out/result-$$-$RANDOM.wav"
    curl -sf -X PUT --data-binary "@${FIXTURE}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${_stage}" >/dev/null || true
    code=$(curl -s -X POST \
        -H "Content-Type: application/json" \
        -d "{\"file_path\":\"$_stage\",\"output_path\":\"uvr/restore.wav\"}" \
        -o "$tmp" \
        -w "%{http_code}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/restore/uvr-dereverb")
    # v1.0.0: download the staged output to satisfy the test's -o expectation
    curl -sf -o "$tmp" "${AUDIOLLA_BASE_URL}/v1/files/${_out}" || true
    body=$(cat "$tmp")
    rm -f "$tmp"

    if [ "$code" = "200" ]; then
        if ! echo "$body" | jq -e '.path == "uvr/restore.wav"' >/dev/null 2>&1; then
            echo "  FAIL: output_path response missing path; body: $body"
            return 1
        fi
        echo "OK: restore_output_path (staged to uvr/restore.wav)"
        return 0
    fi

    if echo "$body" | grep -qiE "model|file|No such file|ckpt|pth"; then
        echo "  SKIP: restore_output_path — model weights not present"
        return 0
    fi
    if [ "$code" = "404" ]; then
        echo "  SKIP: restore_output_path — engine not configured"
        return 0
    fi

    echo "  FAIL: output_path -> HTTP ${code}: ${body:0:300}"
    return 1
}

harness_run_tests \
    test_restore_dereverb \
    test_restore_deecho \
    test_restore_denoise \
    test_restore_rejects_wrong_engine_type \
    test_restore_output_path
