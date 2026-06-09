"""Resolve an audio-endpoint input to (bytes, filename).

Every REST audio endpoint accepts exactly one of three input modes:

    file       — multipart upload (raw bytes in the request)
    file_path  — relative path under the /v1/files staging area
    file_url   — remote URL fetched server-side (subject to fetch policy)

Zero or more-than-one of these = 400. The resolver normalises all three
to a (bytes, filename) tuple so the actual audio engines never know which
mode was used.
"""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

from . import config, fetch
from . import files as files_mod
import logging

_log = logging.getLogger("audiolla.input_resolver")

_log = logging.getLogger("audiolla.input_resolver")


def _has_upload(file: UploadFile | None) -> bool:
    """An UploadFile arrives even when the field was empty; treat a None
    or filename-less upload as 'no upload provided'."""
    if file is None:
        return False
    name = getattr(file, "filename", None)
    return bool(name)


async def resolve_input(
    *,
    file: UploadFile | None,
    file_path: str | None,
    file_url: str | None,
    field_prefix: str = "file",
) -> tuple[bytes, str]:
    """Return (bytes, filename) for whichever input mode the caller used.

    Enforces exactly-one-of semantics and applies size cap + fetch policy.
    Raises HTTPException with the appropriate status code on any failure
    so endpoints can `await resolve_input(...)` directly.
    """
    has_upload = _has_upload(file)
    has_path = bool(file_path)
    has_url = bool(file_url)
    n = int(has_upload) + int(has_path) + int(has_url)

    if n == 0:
        raise HTTPException(
            status_code=400,
            detail=(
                f"must provide exactly one of: {field_prefix}, "
                f"{field_prefix}_path, {field_prefix}_url"
            ),
        )
    if n > 1:
        raise HTTPException(
            status_code=400,
            detail=(
                f"provide only one of: {field_prefix}, "
                f"{field_prefix}_path, {field_prefix}_url"
            ),
        )

    if has_upload:
        assert file is not None  # for type checker
        return await _read_upload(file)
    if has_path:
        assert file_path is not None
        return _read_staged(file_path)
    assert file_url is not None
    return await _fetch_url(file_url)


async def _read_upload(file: UploadFile) -> tuple[bytes, str]:
    raw = await file.read()
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"upload too large ({len(raw)} bytes > "
                f"{config.MAX_UPLOAD_BYTES})"
            ),
        )
    if not raw:
        raise HTTPException(status_code=400, detail="uploaded file is empty")
    return raw, file.filename or "audio"


def _read_staged(path: str) -> tuple[bytes, str]:
    try:
        rel = files_mod.sanitize_path(path)
        src = files_mod.resolve_under(config.FILES_DIR, rel)
    except files_mod.FilePathError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if src.is_symlink() or not src.is_file():
        raise HTTPException(
            status_code=404, detail=f"staged file not found: {rel}"
        )
    try:
        data = src.read_bytes()
    except OSError as exc:
        raise HTTPException(
            status_code=500, detail=f"read failed: {exc}"
        ) from exc
    if len(data) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"staged file too large ({len(data)} bytes > "
                f"{config.MAX_UPLOAD_BYTES})"
            ),
        )
    if not data:
        raise HTTPException(
            status_code=400, detail=f"staged file is empty: {rel}"
        )
    return data, src.name


async def _fetch_url(url: str) -> tuple[bytes, str]:
    try:
        return await fetch.fetch_to_bytes(url, config.MAX_UPLOAD_BYTES)
    except fetch.FetchError as exc:
        # Policy / network / size errors are all client problems from the
        # caller's perspective — they passed a URL that didn't pan out.
        raise HTTPException(status_code=400, detail=str(exc)) from exc
