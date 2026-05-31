#!/bin/bash
# MCP streamable-HTTP transport end-to-end.
#
#     bash tests/integration/e2e_mcp.sh

set -eo pipefail

_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=harness.sh
source "${_DIR}/harness.sh"
# shellcheck source=common.sh
source "${_DIR}/common.sh"

harness_start "librosa-analyze,sox-transform"

MCP_URL="${AUDIOLLA_BASE_URL}/v1/mcp"

# Stateless MCP server returns a session id in headers, but for these
# probes we use stateless JSON responses (one-shot init).
_mcp_post() {
    local payload="$1"
    curl -s --max-time 30 \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -X POST -d "$payload" "${MCP_URL}"
}

# ── initialize handshake returns protocol metadata ───────────────────────────

test_mcp_initialize() {
    local body
    body=$(_mcp_post '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"e2e","version":"0"}}}')
    if ! echo "$body" | jq -e '.result.serverInfo.name == "audiolla"' >/dev/null 2>&1; then
        echo "  FAIL: serverInfo.name != audiolla"
        echo "  body: $body"
        return 1
    fi
    echo "OK: mcp_initialize"
}

# ── slash-rewrite middleware: bare /v1/mcp routes the same as /v1/mcp/ ───────

test_mcp_no_trailing_slash() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -X POST "${AUDIOLLA_BASE_URL}/v1/mcp" \
        -d '{"jsonrpc":"2.0","id":2,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"e2e","version":"0"}}}')
    assert_eq "$code" "200" "POST /v1/mcp (no trailing slash) -> 200" || return 1
    echo "OK: mcp_no_trailing_slash"
}

# ── healthz unaffected by MCP mount ──────────────────────────────────────────

test_mcp_does_not_break_healthz() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 \
        "${AUDIOLLA_BASE_URL}/healthz")
    assert_eq "$code" "200" "/healthz still 200 with MCP mounted" || return 1
    echo "OK: mcp_does_not_break_healthz"
}

# ── MCP endpoint accepts a non-init request and returns a JSON-RPC error ─────
# A pre-init tools/list call should NOT 500 — it should return a JSON-RPC
# error (Bad Request or similar) per the protocol.

test_mcp_pre_init_returns_protocol_error() {
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 10 \
        -H "Content-Type: application/json" \
        -H "Accept: application/json, text/event-stream" \
        -X POST "${MCP_URL}" \
        -d '{"jsonrpc":"2.0","id":3,"method":"tools/list"}')
    # 400 / 200 are both fine; the server must NOT 500.
    if [ "$code" = "500" ]; then
        echo "  FAIL: pre-init tools/list -> 500 (should be 200 or 400)"
        return 1
    fi
    echo "OK: mcp_pre_init_returns_protocol_error (HTTP $code)"
}

harness_run_tests \
    test_mcp_initialize \
    test_mcp_no_trailing_slash \
    test_mcp_does_not_break_healthz \
    test_mcp_pre_init_returns_protocol_error
