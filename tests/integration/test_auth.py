"""End-to-end tests for the bearer-token auth middleware.

These only run when ``AUDIOLLA_AUTH_TOKEN`` is set in the caller's
environment — the conftest forwards that env var to the container at
session start, so the running harness will actually require a token.
Without the env var the middleware is disabled and there's nothing to
test.

The fixture-provided ``client`` already has the correct token in its
default headers; the tests below construct *new* httpx clients to
exercise the missing / wrong-token paths without inheriting auth.
"""

from __future__ import annotations

import os

import httpx
import pytest

_AUTH_TOKEN = os.environ.get("AUDIOLLA_AUTH_TOKEN", "")

pytestmark = pytest.mark.skipif(
    not _AUTH_TOKEN,
    reason="needs AUDIOLLA_AUTH_TOKEN (forwarded to the harness container)",
)


def _bare_client(base_url: str, *, token: str | None = None) -> httpx.Client:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return httpx.Client(
        base_url=base_url,
        headers=headers,
        timeout=httpx.Timeout(connect=10.0, read=10.0, write=10.0, pool=10.0),
    )


def test_healthz_no_auth(audiolla_url: str) -> None:
    """/healthz is exempt — no auth header still → 200."""
    with _bare_client(audiolla_url) as c:
        r = c.get("/healthz")
    assert r.status_code == 200, r.text


def test_missing_auth_401(audiolla_url: str) -> None:
    """No Authorization header → 401."""
    with _bare_client(audiolla_url) as c:
        r = c.get("/v1/engines")
    assert r.status_code == 401, r.text


def test_wrong_token_401(audiolla_url: str) -> None:
    """Bearer with a non-matching token → 401."""
    with _bare_client(audiolla_url, token="not-the-real-token") as c:
        r = c.get("/v1/engines")
    assert r.status_code == 401, r.text


def test_wrong_scheme_401(audiolla_url: str) -> None:
    """Basic <token> instead of Bearer <token> → 401."""
    with httpx.Client(
        base_url=audiolla_url,
        headers={"Authorization": f"Basic {_AUTH_TOKEN}"},
        timeout=httpx.Timeout(10.0),
    ) as c:
        r = c.get("/v1/engines")
    assert r.status_code == 401, r.text


def test_correct_token_200(audiolla_url: str) -> None:
    """Correct Bearer token → 200 from /v1/engines."""
    with _bare_client(audiolla_url, token=_AUTH_TOKEN) as c:
        r = c.get("/v1/engines")
    assert r.status_code == 200, r.text


def test_401_body_is_valid_json(audiolla_url: str) -> None:
    """401 responses ship a JSON body with a `detail` string."""
    with _bare_client(audiolla_url) as c:
        r = c.get("/v1/engines")
    assert r.status_code == 401
    body = r.json()
    assert isinstance(body["detail"], str)
