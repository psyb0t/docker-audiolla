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

# ── v1.0.0 helpers — JSON-body POST + staged-file upload ───────────────────

audiolla_upload() {
    local local_path="$1" stage_path="$2"
    if [ ! -f "$local_path" ]; then
        echo "  FAIL: audiolla_upload: local file not found: $local_path" >&2
        return 1
    fi
    curl -sf --max-time 60 -X PUT \
        --data-binary "@${local_path}" \
        -H "Content-Type: application/octet-stream" \
        "${AUDIOLLA_BASE_URL}/v1/files/${stage_path}"
}

audiolla_post_json() {
    local path="$1" body="$2"
    local tmp
    tmp=$(mktemp -t audiolla_resp.XXXXXX) || return 2
    local code
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 900 \
        -X POST -H "Content-Type: application/json" \
        -d "$body" \
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

# Legacy helper — auto-upload + JSON-POST shim. Builds JSON body from
# key=value args plus an auto output_path if none provided.
audiolla_post_audio() {
    local path="$1" fixture="$2"
    shift 2
    local stage="e2e/$(basename "$fixture")-$$"
    audiolla_upload "$fixture" "$stage" >/dev/null || return 1
    local json='{"file_path":"'"$stage"'"'
    local has_output=0
    local kv key val
    for kv in "$@"; do
        key="${kv%%=*}"
        val="${kv#*=}"
        if [ "$key" = "output_path" ] || [ "$key" = "output_url" ]; then
            has_output=1
        fi
        if [[ "$val" =~ ^-?[0-9]+(\.[0-9]+)?$ ]]; then
            json="${json},\"${key}\":${val}"
        elif [ "$val" = "true" ] || [ "$val" = "false" ]; then
            json="${json},\"${key}\":${val}"
        else
            json="${json},\"${key}\":\"${val}\""
        fi
    done
    if [ "$has_output" = "0" ]; then
        json="${json},\"output_path\":\"e2e/out-$$-${RANDOM}.wav\""
    fi
    json="${json}}"
    audiolla_post_json "$path" "$json"
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
