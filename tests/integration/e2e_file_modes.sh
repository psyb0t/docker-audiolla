#!/bin/bash
# End-to-end tests for the file_path / output_path / file_url / output_url
# input/output modes on the audio endpoints. Uses /v1/audio/transform
# because sox-transform is CPU-light and predictable — these tests are
# about the file-resolution and output-routing paths, not the engine.
#
#     bash tests/integration/e2e_file_modes.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

FIXTURE="${_DIR}/.fixtures/audio.wav"

# Enable URL fetching against the audiolla container's own loopback so we
# don't need an external HTTP mock. The container reaches itself at
# 127.0.0.1:8000 (the host port mapping is irrelevant inside the netns).
# Allowlist + allow-private both required because 127.0.0.1 is loopback.
export AUDIOLLA_FETCH_MODE=allowlist
export AUDIOLLA_FETCH_HOSTS="127.0.0.1"
export AUDIOLLA_FETCH_ALLOW_PRIVATE=true
export AUDIOLLA_FETCH_SCHEMES=http,https

harness_start "sox-transform"

# ── helpers ─────────────────────────────────────────────────────────────────

# Stage the fixture under a known path so subsequent tests can reference it.
STAGED_PATH="modes/in.wav"

setup_staged_fixture() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X PUT -H "Content-Type: application/octet-stream" \
        --data-binary "@${FIXTURE}" \
        "${AUDIOLLA_BASE_URL}/v1/files/${STAGED_PATH}")
    if [ "$code" != "201" ]; then
        echo "  FAIL: staging the fixture returned ${code}, expected 201"
        return 1
    fi
}

# ── file_path: feed a staged file into transform, get audio back ─────────────

test_transform_with_file_path() {
    setup_staged_fixture || return 1
    local code tmp
    tmp=$(mktemp)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 60 \
        -X POST \
        -F "file_path=${STAGED_PATH}" \
        -F 'operations=[{"op":"gain","params":{"db":-3}}]' \
        -F "output_format=wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    assert_eq "$code" "200" "transform file_path -> 200" || { rm -f "$tmp"; return 1; }
    if ! head -c 4 "$tmp" | grep -q "RIFF"; then
        echo "  FAIL: response is not a WAV"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: transform_with_file_path"
}

# ── file_path 404 when the staged file doesn't exist ─────────────────────────

test_file_path_missing_404() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=nope/does/not/exist.wav" \
        -F 'operations=[]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    assert_eq "$code" "404" "file_path missing -> 404" || return 1
    echo "OK: file_path_missing_404"
}

# ── output_path: process AND write back to staging in one call ──────────────

test_transform_with_output_path() {
    setup_staged_fixture || return 1
    local code body
    body=$(curl -s -o /tmp/audiolla-modes-resp.$$ -w "%{http_code}" \
        --max-time 60 -X POST \
        -F "file_path=${STAGED_PATH}" \
        -F 'operations=[{"op":"gain","params":{"db":-3}}]' \
        -F "output_format=wav" \
        -F "output_path=modes/out.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    code="$body"
    body=$(cat /tmp/audiolla-modes-resp.$$ 2>/dev/null)
    rm -f /tmp/audiolla-modes-resp.$$
    assert_eq "$code" "200" "transform output_path -> 200" || return 1
    if ! echo "$body" | grep -q '"path":"modes/out.wav"'; then
        echo "  FAIL: response missing path field; got: $body"
        return 1
    fi
    if ! echo "$body" | grep -q '"size":'; then
        echo "  FAIL: response missing size field; got: $body"
        return 1
    fi

    # The written file must actually be retrievable via GET /v1/files.
    local fetched
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/modes/out.wav")
    assert_eq "$code" "200" "GET output file -> 200" || { rm -f "$fetched"; return 1; }
    if ! head -c 4 "$fetched" | grep -q "RIFF"; then
        echo "  FAIL: written output is not a WAV"
        rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: transform_with_output_path"
}

# ── output_path with traversal rejected ──────────────────────────────────────

test_output_path_traversal_rejected() {
    setup_staged_fixture || return 1
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=${STAGED_PATH}" \
        -F 'operations=[]' \
        -F "output_path=../escape.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    assert_eq "$code" "400" "output_path traversal -> 400" || return 1
    echo "OK: output_path_traversal_rejected"
}

# ── output_path + output_url both set → 400 (exactly-one-of) ─────────────────

test_output_path_and_url_mutually_exclusive() {
    setup_staged_fixture || return 1
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 30 \
        -X POST \
        -F "file_path=${STAGED_PATH}" \
        -F 'operations=[]' \
        -F "output_path=modes/x.wav" \
        -F "output_url=http://127.0.0.1:8000/v1/files/y.wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    assert_eq "$code" "400" "output_path + output_url -> 400" || return 1
    echo "OK: output_path_and_url_mutually_exclusive"
}

# ── file_url: fetch from the audiolla container's own /v1/files endpoint ─────
# Loopback because the container can reach itself at 127.0.0.1:8000. The
# allowlist + ALLOW_PRIVATE config above lets this URL pass policy.

test_file_url_loopback_fetch() {
    setup_staged_fixture || return 1
    local code tmp
    tmp=$(mktemp)
    code=$(curl -s -o "$tmp" -w "%{http_code}" --max-time 60 \
        -X POST \
        -F "file_url=http://127.0.0.1:8000/v1/files/${STAGED_PATH}" \
        -F 'operations=[{"op":"gain","params":{"db":-3}}]' \
        -F "output_format=wav" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    assert_eq "$code" "200" "transform file_url -> 200" || { rm -f "$tmp"; return 1; }
    if ! head -c 4 "$tmp" | grep -q "RIFF"; then
        echo "  FAIL: response is not a WAV"
        rm -f "$tmp"; return 1
    fi
    rm -f "$tmp"
    echo "OK: file_url_loopback_fetch"
}

# ── file_url to a host NOT in the allowlist → 400 ────────────────────────────

test_file_url_outside_allowlist_400() {
    local code body
    body=$(curl -s -o /tmp/audiolla-modes-resp.$$ -w "%{http_code}" \
        --max-time 30 -X POST \
        -F "file_url=https://evil.example.com/x.wav" \
        -F 'operations=[]' \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    code="$body"
    body=$(cat /tmp/audiolla-modes-resp.$$ 2>/dev/null)
    rm -f /tmp/audiolla-modes-resp.$$
    assert_eq "$code" "400" "file_url not allowlisted -> 400" || return 1
    if ! echo "$body" | grep -qi "allowlist"; then
        echo "  FAIL: detail does not mention allowlist; got: $body"
        return 1
    fi
    echo "OK: file_url_outside_allowlist_400"
}

# ── output_url: PUT the result to the audiolla container's own /v1/files ─────

test_output_url_loopback_put() {
    setup_staged_fixture || return 1
    local target="http://127.0.0.1:8000/v1/files/modes/out_via_url.wav"
    local code body
    body=$(curl -s -o /tmp/audiolla-modes-resp.$$ -w "%{http_code}" \
        --max-time 60 -X POST \
        -F "file_path=${STAGED_PATH}" \
        -F 'operations=[{"op":"gain","params":{"db":-3}}]' \
        -F "output_format=wav" \
        -F "output_url=${target}" \
        "${AUDIOLLA_BASE_URL}/v1/audio/transform")
    code="$body"
    body=$(cat /tmp/audiolla-modes-resp.$$ 2>/dev/null)
    rm -f /tmp/audiolla-modes-resp.$$
    assert_eq "$code" "200" "transform output_url -> 200" || return 1
    if ! echo "$body" | grep -q '"url":'; then
        echo "  FAIL: response missing url field; got: $body"
        return 1
    fi
    if ! echo "$body" | grep -q '"size":'; then
        echo "  FAIL: response missing size field; got: $body"
        return 1
    fi

    # The PUT target was a /v1/files endpoint — so the file should now be
    # retrievable via the staging GET.
    local fetched
    fetched=$(mktemp)
    code=$(curl -s -o "$fetched" -w "%{http_code}" --max-time 30 \
        "${AUDIOLLA_BASE_URL}/v1/files/modes/out_via_url.wav")
    assert_eq "$code" "200" "GET via-url file -> 200" || { rm -f "$fetched"; return 1; }
    if ! head -c 4 "$fetched" | grep -q "RIFF"; then
        echo "  FAIL: written output is not a WAV"
        rm -f "$fetched"; return 1
    fi
    rm -f "$fetched"
    echo "OK: output_url_loopback_put"
}

harness_run_tests \
    test_transform_with_file_path \
    test_file_path_missing_404 \
    test_transform_with_output_path \
    test_output_path_traversal_rejected \
    test_output_path_and_url_mutually_exclusive \
    test_file_url_loopback_fetch \
    test_file_url_outside_allowlist_400 \
    test_output_url_loopback_put
