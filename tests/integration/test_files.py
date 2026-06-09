"""End-to-end tests for the ``/v1/files`` staging API.

PUT round-trips, GET, LIST, DELETE, and the path-safety rails. No engine
markers — the file store is engine-independent.
"""

from __future__ import annotations

import secrets

import httpx


def test_files_put_get_roundtrip(client: httpx.Client) -> None:
    """PUT then GET returns the exact bytes uploaded."""
    body = b"hello audiolla files"
    path = f"foo/bar/hello-{secrets.token_hex(4)}.txt"
    put = client.put(
        f"/v1/files/{path}",
        content=body,
        headers={"Content-Type": "application/octet-stream"},
    )
    assert put.status_code == 201, put.text

    got = client.get(f"/v1/files/{path}")
    assert got.status_code == 200
    assert got.content == body


def test_files_list_includes_put(client: httpx.Client) -> None:
    """Newly-staged file appears in the listing."""
    path = f"foo/list-{secrets.token_hex(4)}.txt"
    put = client.put(
        f"/v1/files/{path}",
        content=b"x",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert put.status_code == 201, put.text

    listing = client.get("/v1/files")
    assert listing.status_code == 200
    body = listing.json()
    assert isinstance(body["files"], list)
    paths = [f["path"] for f in body["files"]]
    assert path in paths


def test_files_delete(client: httpx.Client) -> None:
    """DELETE removes the file; subsequent GET → 404."""
    path = f"foo/delete-{secrets.token_hex(4)}.txt"
    client.put(
        f"/v1/files/{path}",
        content=b"x",
        headers={"Content-Type": "application/octet-stream"},
    )
    r = client.delete(f"/v1/files/{path}")
    assert r.status_code == 200, r.text

    r2 = client.get(f"/v1/files/{path}")
    assert r2.status_code == 404


def test_files_path_traversal_rejected(client: httpx.Client) -> None:
    """URL-encoded `..` in the path → 400 or 404 (sanitize rejects either way)."""
    r = client.put(
        "/v1/files/%2e%2e/escape",
        content=b"x",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code in (400, 404), r.text


def test_files_empty_path_rejected(client: httpx.Client) -> None:
    """Empty path component → 400 / 404 / 405."""
    r = client.put(
        "/v1/files/",
        content=b"x",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert r.status_code in (400, 404, 405), r.text


def test_files_get_unknown_404(client: httpx.Client) -> None:
    """GET on a path that was never staged → 404."""
    r = client.get(f"/v1/files/nope/never-{secrets.token_hex(4)}.bin")
    assert r.status_code == 404
