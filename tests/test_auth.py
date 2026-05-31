"""Unit tests for audiolla.auth — bearer-token middleware via a minimal
ASGI scope/send mock. No FastAPI / Starlette test client needed."""

from __future__ import annotations

import json

import pytest

from audiolla.auth import BearerAuthMiddleware


class _Capture:
    """ASGI send callable that records every message."""

    def __init__(self) -> None:
        self.messages: list[dict] = []

    async def __call__(self, message: dict) -> None:
        self.messages.append(message)

    @property
    def status(self) -> int | None:
        for m in self.messages:
            if m.get("type") == "http.response.start":
                return int(m["status"])
        return None

    @property
    def body(self) -> bytes:
        for m in self.messages:
            if m.get("type") == "http.response.body":
                return m["body"]
        return b""


async def _inner_ok(scope, receive, send):
    """Trivial ASGI app that always returns 200 + 'OK'."""
    await send({
        "type": "http.response.start",
        "status": 200,
        "headers": [(b"content-type", b"text/plain")],
    })
    await send({"type": "http.response.body", "body": b"OK"})


def _http_scope(path: str = "/v1/engines", headers: list[tuple[bytes, bytes]] | None = None) -> dict:
    return {
        "type": "http",
        "method": "GET",
        "path": path,
        "headers": headers or [],
    }


# ── happy path: empty token disables auth ────────────────────────────────────

@pytest.mark.asyncio
async def test_empty_token_passes_through() -> None:
    mw = BearerAuthMiddleware(_inner_ok, token="")
    cap = _Capture()
    await mw(_http_scope(), lambda: None, cap)
    assert cap.status == 200


# ── /healthz exempt regardless of auth state ────────────────────────────────

@pytest.mark.asyncio
async def test_healthz_exempt_without_token() -> None:
    mw = BearerAuthMiddleware(_inner_ok, token="secret")
    cap = _Capture()
    await mw(_http_scope("/healthz"), lambda: None, cap)
    assert cap.status == 200


# ── OPTIONS exempt (CORS preflight) ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_options_exempt() -> None:
    mw = BearerAuthMiddleware(_inner_ok, token="secret")
    cap = _Capture()
    scope = _http_scope("/v1/engines")
    scope["method"] = "OPTIONS"
    await mw(scope, lambda: None, cap)
    assert cap.status == 200


# ── missing header → 401 with JSON body ──────────────────────────────────────

@pytest.mark.asyncio
async def test_missing_header_401() -> None:
    mw = BearerAuthMiddleware(_inner_ok, token="secret")
    cap = _Capture()
    await mw(_http_scope(), lambda: None, cap)
    assert cap.status == 401
    parsed = json.loads(cap.body.decode("utf-8"))
    assert "detail" in parsed
    assert "missing" in parsed["detail"].lower()


# ── wrong token → 401 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wrong_token_401() -> None:
    mw = BearerAuthMiddleware(_inner_ok, token="secret")
    cap = _Capture()
    scope = _http_scope(headers=[(b"authorization", b"Bearer wrong")])
    await mw(scope, lambda: None, cap)
    assert cap.status == 401


# ── wrong scheme (Basic) → 401 ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_wrong_scheme_401() -> None:
    mw = BearerAuthMiddleware(_inner_ok, token="secret")
    cap = _Capture()
    scope = _http_scope(headers=[(b"authorization", b"Basic secret")])
    await mw(scope, lambda: None, cap)
    assert cap.status == 401


# ── correct token → passes ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_correct_token_passes() -> None:
    mw = BearerAuthMiddleware(_inner_ok, token="secret")
    cap = _Capture()
    scope = _http_scope(headers=[(b"authorization", b"Bearer secret")])
    await mw(scope, lambda: None, cap)
    assert cap.status == 200


# ── 401 body is valid JSON with sane detail ──────────────────────────────────

@pytest.mark.asyncio
async def test_401_body_is_valid_json_with_quotes() -> None:
    # Repro for the old f-string interpolation bug: detail strings with
    # double-quotes / backslashes / newlines must JSON-encode correctly.
    # The middleware doesn't expose this attack surface to callers, but
    # the helper is the right place to defend.
    from audiolla.auth import _send_401

    cap = _Capture()
    await _send_401(cap, 'detail with "quotes" and \\backslash and \nnewline')
    parsed = json.loads(cap.body.decode("utf-8"))
    assert parsed["detail"] == 'detail with "quotes" and \\backslash and \nnewline'
