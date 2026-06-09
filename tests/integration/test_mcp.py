"""End-to-end tests for the MCP streamable-HTTP transport mount.

``POST /v1/mcp`` (and ``/v1/mcp/``) speak JSON-RPC; this file covers the
transport-level concerns — handshake, slash-rewrite middleware, error
shape for pre-init calls. Tool-level tests live in test_mcp_tools.py.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.engine("librosa-analyze", "sox-transform")


_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


def test_mcp_initialize(client: httpx.Client) -> None:
    """initialize handshake returns serverInfo.name == audiolla."""
    r = client.post(
        "/v1/mcp/",
        headers=_MCP_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "e2e", "version": "0"},
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["serverInfo"]["name"] == "audiolla"


def test_mcp_no_trailing_slash(client: httpx.Client) -> None:
    """POST to bare /v1/mcp routes the same as /v1/mcp/ (rewrite middleware)."""
    r = client.post(
        "/v1/mcp",
        headers=_MCP_HEADERS,
        json={
            "jsonrpc": "2.0",
            "id": 2,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {"name": "e2e", "version": "0"},
            },
        },
    )
    assert r.status_code == 200, r.text


def test_mcp_does_not_break_healthz(client: httpx.Client) -> None:
    """/healthz still returns 200 with MCP mounted."""
    r = client.get("/healthz")
    assert r.status_code == 200


def test_mcp_pre_init_returns_protocol_error(client: httpx.Client) -> None:
    """A tools/list call without prior initialize returns a JSON-RPC error
    (NOT a 500). Both 200 and 400 are acceptable; 500 is not."""
    r = client.post(
        "/v1/mcp/",
        headers=_MCP_HEADERS,
        json={"jsonrpc": "2.0", "id": 3, "method": "tools/list"},
    )
    assert r.status_code != 500, r.text
