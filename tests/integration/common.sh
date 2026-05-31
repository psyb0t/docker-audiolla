#!/bin/bash
# shellcheck shell=bash
# HTTP helpers + assertions shared across audiolla integration test files.
#
# Container lifecycle lives in harness.sh — this file is just transport helpers
# that talk to whatever $AUDIOLLA_BASE_URL points at. Source order in a test:
#
#     source harness.sh
#     source common.sh
#     harness_start "..."

# ── assertions ───────────────────────────────────────────────────────────────

assert_eq() {
    local actual="$1" expected="$2" name="$3"
    if [ "$actual" = "$expected" ]; then
        echo "  OK: $name"
        return 0
    fi
    echo "  FAIL: $name: expected '$expected', got '$actual'"
    return 1
}

assert_contains() {
    local actual="$1" expected="$2" name="$3"
    if [[ "$actual" == *"$expected"* ]]; then
        echo "  OK: $name"
        return 0
    fi
    echo "  FAIL: $name: expected to contain '$expected'"
    echo "  actual: ${actual:0:500}"
    return 1
}

assert_not_empty() {
    local actual="$1" name="$2"
    if [ -n "$actual" ]; then
        echo "  OK: $name"
        return 0
    fi
    echo "  FAIL: $name: expected non-empty output"
    return 1
}

# ── HTTP helpers ─────────────────────────────────────────────────────────────

audiolla_get() {
    curl -sf --max-time 30 "${AUDIOLLA_BASE_URL}$1"
}

audiolla_method() {
    local method="$1" path="$2"
    curl -sf --max-time 30 -X "$method" "${AUDIOLLA_BASE_URL}${path}"
}

audiolla_method_status() {
    local method="$1" path="$2"
    curl -s -o /dev/null -w "%{http_code}" --max-time 30 -X "$method" "${AUDIOLLA_BASE_URL}${path}"
}

# Multipart upload to an audio endpoint.
#
# args:
#   $1 = path (e.g. /v1/audio/separate)
#   $2 = path to local audio fixture
#   $3... = extra "key=value" form fields
#
# Successful HTTP 2xx → body on stdout, exit 0.
# Anything else      → stderr explains, exit 1.
audiolla_post_audio() {
    local path="$1" fixture="$2"
    shift 2

    local extras=()
    local kv
    for kv in "$@"; do
        extras+=(-F "$kv")
    done

    local tmp
    tmp=$(mktemp -t audiolla_resp.XXXXXX) || return 2
    local code
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 900 \
        "${extras[@]}" \
        -F "file=@${fixture}" \
        "${AUDIOLLA_BASE_URL}${path}" 2>/dev/null) || {
        rm -f "$tmp"
        return 2
    }
    if [ "$code" -lt 200 ] || [ "$code" -ge 300 ]; then
        echo "  HTTP $code: $(head -c 500 "$tmp")" >&2
        rm -f "$tmp"
        return 1
    fi
    cat "$tmp"
    rm -f "$tmp"
}

# Check that a response is a valid audio file (non-empty, has expected magic).
assert_audio_bytes() {
    local path="$1" name="$2"
    if [ ! -s "$path" ]; then
        echo "  FAIL: $name: file is empty"
        return 1
    fi
    echo "  OK: $name ($(wc -c < "$path") bytes)"
}
