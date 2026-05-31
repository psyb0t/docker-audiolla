"""Unit tests for audiolla.input_resolver — exactly-one-of validation
and staged-path resolution. The file_url branch is covered by the fetch
tests + integration tests."""

from __future__ import annotations

from pathlib import Path
import pytest
from fastapi import HTTPException

from audiolla import input_resolver


class _FakeUploadFile:
    """Minimal stand-in for fastapi.UploadFile."""

    def __init__(self, content: bytes, filename: str | None = "x.wav"):
        self._content = content
        self.filename = filename

    async def read(self) -> bytes:
        return self._content


# ── exactly-one validation ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_input_rejects_zero_inputs():
    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=None, file_path=None, file_url=None,
        )
    assert exc.value.status_code == 400
    assert "exactly one" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_resolve_input_rejects_two_inputs():
    up = _FakeUploadFile(b"x")
    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=up, file_path="foo.wav", file_url=None,
        )
    assert exc.value.status_code == 400
    assert "only one" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_resolve_input_rejects_all_three_inputs():
    up = _FakeUploadFile(b"x")
    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=up,
            file_path="foo.wav",
            file_url="https://example.com/x",
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_resolve_input_treats_empty_upload_as_absent():
    """An UploadFile with no filename = field wasn't really provided.
    Otherwise the multipart-form-parser default would block file_path."""
    up = _FakeUploadFile(b"", filename=None)
    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=up, file_path=None, file_url=None,
        )
    assert exc.value.status_code == 400
    assert "exactly one" in exc.value.detail.lower()


# ── upload mode ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_input_returns_upload_bytes():
    up = _FakeUploadFile(b"hello-bytes", filename="hello.wav")
    data, name = await input_resolver.resolve_input(
        file=up, file_path=None, file_url=None,
    )
    assert data == b"hello-bytes"
    assert name == "hello.wav"


@pytest.mark.asyncio
async def test_resolve_input_rejects_empty_upload():
    up = _FakeUploadFile(b"", filename="empty.wav")
    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=up, file_path=None, file_url=None,
        )
    assert exc.value.status_code == 400
    assert "empty" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_resolve_input_rejects_oversized_upload(monkeypatch):
    monkeypatch.setattr(input_resolver.config, "MAX_UPLOAD_BYTES", 10)
    up = _FakeUploadFile(b"x" * 50, filename="big.wav")
    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=up, file_path=None, file_url=None,
        )
    assert exc.value.status_code == 413


# ── staged-path mode ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_input_reads_staged_file(tmp_path, monkeypatch):
    files_dir: Path = tmp_path / "files"
    files_dir.mkdir()
    target = files_dir / "track.wav"
    target.write_bytes(b"staged-bytes")
    monkeypatch.setattr(input_resolver.config, "FILES_DIR", files_dir)

    data, name = await input_resolver.resolve_input(
        file=None, file_path="track.wav", file_url=None,
    )
    assert data == b"staged-bytes"
    assert name == "track.wav"


@pytest.mark.asyncio
async def test_resolve_input_staged_404_when_missing(tmp_path, monkeypatch):
    files_dir: Path = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setattr(input_resolver.config, "FILES_DIR", files_dir)

    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=None, file_path="nope.wav", file_url=None,
        )
    assert exc.value.status_code == 404
    assert "not found" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_resolve_input_staged_rejects_traversal(tmp_path, monkeypatch):
    files_dir: Path = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setattr(input_resolver.config, "FILES_DIR", files_dir)

    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=None, file_path="../etc/passwd", file_url=None,
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_resolve_input_staged_rejects_symlink_to_outside(
    tmp_path, monkeypatch,
):
    """A symlink that resolves outside FILES_DIR gets caught by
    resolve_under() (400: path escapes), not by the is_symlink() 404
    check — `Path.resolve()` follows the link before the relative-to
    test. Either way the file isn't returned, which is the point."""
    files_dir: Path = tmp_path / "files"
    files_dir.mkdir()
    outside = tmp_path / "outside.wav"
    outside.write_bytes(b"secret")
    link = files_dir / "linked.wav"
    link.symlink_to(outside)
    monkeypatch.setattr(input_resolver.config, "FILES_DIR", files_dir)

    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=None, file_path="linked.wav", file_url=None,
        )
    assert exc.value.status_code == 400
    assert "escapes" in exc.value.detail.lower()




@pytest.mark.asyncio
async def test_resolve_input_staged_rejects_empty_file(tmp_path, monkeypatch):
    files_dir: Path = tmp_path / "files"
    files_dir.mkdir()
    (files_dir / "empty.wav").write_bytes(b"")
    monkeypatch.setattr(input_resolver.config, "FILES_DIR", files_dir)

    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=None, file_path="empty.wav", file_url=None,
        )
    assert exc.value.status_code == 400


# ── URL mode ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_resolve_input_url_propagates_policy_error(monkeypatch):
    """A FetchError from the underlying fetcher should surface as a
    400 with the message intact — clients need to see what policy bit."""
    # IMPORTANT: use input_resolver.fetch.FetchError, not the top-level
    # `audiolla.fetch.FetchError` — other tests (test_fetch) reload the
    # config + fetch modules to test policy combos, which detaches the
    # `audiolla.fetch.FetchError` symbol from the one input_resolver
    # imported. Using the resolver's own reference keeps the except
    # clause's identity check working.
    async def boom(url, cap):
        raise input_resolver.fetch.FetchError("URL fetch/upload is disabled")

    monkeypatch.setattr(input_resolver.fetch, "fetch_to_bytes", boom)
    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=None,
            file_path=None,
            file_url="https://example.com/x",
        )
    assert exc.value.status_code == 400
    assert "disabled" in exc.value.detail.lower()


@pytest.mark.asyncio
async def test_resolve_input_url_returns_bytes_and_name(monkeypatch):
    async def fake_fetch(url, cap):
        return b"fetched-bytes", "remote.wav"

    monkeypatch.setattr(input_resolver.fetch, "fetch_to_bytes", fake_fetch)
    data, name = await input_resolver.resolve_input(
        file=None, file_path=None, file_url="https://example.com/x",
    )
    assert data == b"fetched-bytes"
    assert name == "remote.wav"


# ── field_prefix is reflected in error messages ──────────────────────────────

@pytest.mark.asyncio
async def test_resolve_input_field_prefix_in_errors():
    with pytest.raises(HTTPException) as exc:
        await input_resolver.resolve_input(
            file=None, file_path=None, file_url=None,
            field_prefix="reference",
        )
    detail = exc.value.detail.lower()
    assert "reference" in detail
    assert "reference_path" in detail
    assert "reference_url" in detail
