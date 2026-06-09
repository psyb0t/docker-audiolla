"""Optional bearer-token auth for the ASGI app.

When ``config.AUTH_TOKEN`` is non-empty, every request must include
``Authorization: Bearer <token>`` or it gets 401. Empty token = pass-through.

Exemptions: ``/healthz`` is always reachable so k8s / docker probes keep
working. ``OPTIONS`` requests (CORS preflights) are let through — preflights
aren't allowed to send the Authorization header.
"""

from __future__ import annotations

import hmac
import json
import logging

from starlette.types import ASGIApp, Receive, Scope, Send

_log = logging.getLogger("audiolla.auth")

_EXEMPT_PATHS = frozenset({"/healthz"})
_BEARER_PREFIX = "Bearer "


class BearerAuthMiddleware:
    """ASGI middleware that enforces a static bearer token."""

    def __init__(self, app: ASGIApp, token: str) -> None:
        self.app = app
        self.token = token

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if not self.token:
            await self.app(scope, receive, send)
            return
        if scope["type"] not in ("http", "websocket"):
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in _EXEMPT_PATHS:
            await self.app(scope, receive, send)
            return
        if scope["type"] == "http" and scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return

        token = _extract_bearer(scope)
        if token is None:
            _log.warning(
                "auth: missing bearer header on %s %s",
                scope.get("method", "?"), path,
            )
            await _send_401(send, "missing Authorization: Bearer header")
            return
        if not hmac.compare_digest(token, self.token):
            _log.warning(
                "auth: invalid bearer token on %s %s",
                scope.get("method", "?"), path,
            )
            await _send_401(send, "invalid bearer token")
            return
        await self.app(scope, receive, send)


def _extract_bearer(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"authorization":
            decoded = value.decode("latin-1")
            if decoded.startswith(_BEARER_PREFIX):
                return decoded[len(_BEARER_PREFIX):].strip()
            return None
    return None


async def _send_401(send: Send, detail: str) -> None:
    body = json.dumps({"detail": detail}).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": 401,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"www-authenticate", b"Bearer"),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})
