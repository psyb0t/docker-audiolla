#!/bin/bash
# /v1/files API end-to-end — server-side file staging.
#
# Covers happy paths (PUT / GET / LIST / DELETE) + path-traversal rejection
# + 413 upload-too-large guard. CPU-only, lightest possible engine list.
#
#     bash tests/integration/e2e_files.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

harness_start "librosa-analyze"

# ── PUT / GET round-trip ─────────────────────────────────────────────────────

test_files_put_get_roundtrip() {
    local body code stored
    body="hello audiolla files"
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X PUT -H "Content-Type: application/octet-stream" \
        --data-binary "$body" \
        "${AUDIOLLA_BASE_URL}/v1/files/foo/bar/hello.txt")
    assert_eq "$code" "201" "PUT created -> 201" || return 1

    stored=$(curl -sf --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/foo/bar/hello.txt")
    assert_eq "$stored" "$body" "GET returns the bytes we PUT" || return 1

    echo "OK: files_put_get_roundtrip"
}

# ── LIST shows our staged file ───────────────────────────────────────────────

test_files_list_includes_put() {
    local body
    body=$(curl -sf --max-time 30 "${AUDIOLLA_BASE_URL}/v1/files")
    if ! echo "$body" | jq -e '.files | type == "array"' >/dev/null 2>&1; then
        echo "  FAIL: /v1/files did not return {files: [...]}"
        echo "  body: $body"
        return 1
    fi
    if ! echo "$body" | jq -e '.files | map(select(.path == "foo/bar/hello.txt")) | length == 1' >/dev/null 2>&1; then
        echo "  FAIL: list missing foo/bar/hello.txt"
        echo "  body: $body"
        return 1
    fi
    echo "OK: files_list_includes_put"
}

# ── DELETE removes the file ──────────────────────────────────────────────────

test_files_delete() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X DELETE "${AUDIOLLA_BASE_URL}/v1/files/foo/bar/hello.txt")
    assert_eq "$code" "200" "DELETE -> 200" || return 1

    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/foo/bar/hello.txt")
    assert_eq "$code" "404" "GET on deleted -> 404" || return 1

    echo "OK: files_delete"
}

# ── Path traversal: ../escape → 400 (sanitize_path rejects the segment) ──────

test_files_path_traversal_rejected() {
    local code
    # URL-encode '..' as %2e%2e to bypass naive client-side checks; server
    # should still reject after path normalization.
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X PUT --data-binary "x" \
        "${AUDIOLLA_BASE_URL}/v1/files/%2e%2e/escape")
    if [ "$code" != "400" ] && [ "$code" != "404" ]; then
        echo "  FAIL: traversal expected 400/404, got $code"
        return 1
    fi
    echo "OK: files_path_traversal_rejected (HTTP $code)"
}

# ── Absolute path → 400 (after normalisation, leading slash stripped → reject empty) ─

test_files_empty_path_rejected() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X PUT --data-binary "x" \
        "${AUDIOLLA_BASE_URL}/v1/files/")
    # FastAPI may match /v1/files (no trailing path) → 405 or 400. Accept either.
    if [ "$code" != "400" ] && [ "$code" != "405" ] && [ "$code" != "404" ]; then
        echo "  FAIL: empty path expected 400/404/405, got $code"
        return 1
    fi
    echo "OK: files_empty_path_rejected (HTTP $code)"
}

# ── 413 — upload too large ───────────────────────────────────────────────────
# Default MAX_UPLOAD_BYTES = 200 MB; we can't easily POST 200 MB in CI. Instead
# we exercise the limit by overriding AUDIOLLA_MAX_UPLOAD_BYTES to a tiny value
# via a second short-lived container. This proves the 413 path fires.

test_files_413_upload_too_large() {
    local port name code
    port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
    name="audiolla-413-$$-${RANDOM}"
    docker run -d --rm --name "$name" \
        --user "$(id -u):$(id -g)" \
        -v "${HARNESS_CACHE_DIR}:/data" \
        -e AUDIOLLA_DEVICE=cpu \
        -e AUDIOLLA_ENABLED_ENGINES="librosa-analyze" \
        -e AUDIOLLA_MAX_UPLOAD_BYTES=1024 \
        -p "${port}:8000" "$HARNESS_IMAGE" >/dev/null
    # shellcheck disable=SC2064
    trap "docker rm -f '$name' >/dev/null 2>&1 || true" RETURN

    for _ in $(seq 1 30); do
        curl -sf --max-time 3 "http://127.0.0.1:${port}/healthz" >/dev/null && break
        sleep 1
    done
    code=$(head -c 4096 /dev/urandom \
        | curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
            -X PUT -H "Content-Type: application/octet-stream" \
            --data-binary @- \
            "http://127.0.0.1:${port}/v1/files/big.bin")
    assert_eq "$code" "413" "PUT > MAX_UPLOAD_BYTES -> 413" || return 1
    echo "OK: files_413_upload_too_large"
}

harness_run_tests \
    test_files_put_get_roundtrip \
    test_files_list_includes_put \
    test_files_delete \
    test_files_path_traversal_rejected \
    test_files_empty_path_rejected \
    test_files_413_upload_too_large
