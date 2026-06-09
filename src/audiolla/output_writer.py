"""Write audio output via inline bytes, staging path, or presigned URL.

Every audio-producing endpoint can optionally take `output_path` or
`output_url`. Exactly one OR neither — supplying both is rejected.

If neither is given, the endpoint returns the audio bytes inline with
`Content-Disposition: attachment` (current behaviour, backwards
compatible).

If `output_path` is given, the bytes are written to the staging area
under `FILES_DIR / <path>` and the response is JSON describing what was
written.

If `output_url` is given, the bytes are PUT to the URL (presigned, in the
common case) and the response is JSON describing the destination. The
URL is subject to the same SSRF policy as `file_url` — a hostile
output_url is identical attack surface.
"""

from __future__ import annotations

from fastapi import HTTPException
from fastapi.responses import JSONResponse, Response

from . import config, fetch
from . import files as files_mod
import logging

_log = logging.getLogger("audiolla.output_writer")

_log = logging.getLogger("audiolla.output_writer")


async def write_output(
    payload: bytes,
    *,
    media_type: str,
    filename: str,
    output_path: str | None,
    output_url: str | None,
    extra_inline_headers: dict[str, str] | None = None,
    extra_json: dict | None = None,
) -> Response:
    """Return a `Response` for whichever output mode the caller requested.

    `extra_inline_headers` — added to the inline Response. Ignored when
    `output_path` / `output_url` is used (the metadata goes into the JSON
    body instead — pass via `extra_json`).

    `extra_json` — merged into the JSON body for path/url modes. Ignored
    inline.
    """
    n = int(bool(output_path)) + int(bool(output_url))
    if n > 1:
        raise HTTPException(
            status_code=400,
            detail="provide only one of: output_path, output_url",
        )

    if output_path:
        return _write_staged(
            payload, output_path=output_path, extra_json=extra_json
        )

    if output_url:
        return await _write_url(
            payload,
            output_url=output_url,
            media_type=media_type,
            extra_json=extra_json,
        )

    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if extra_inline_headers:
        headers.update(extra_inline_headers)
    return Response(content=payload, media_type=media_type, headers=headers)


def _write_staged(
    payload: bytes,
    *,
    output_path: str,
    extra_json: dict | None,
) -> JSONResponse:
    try:
        rel = files_mod.sanitize_path(output_path)
        dest = files_mod.resolve_under(config.FILES_DIR, rel)
    except files_mod.FilePathError as exc:
        _log.warning("output_path rejected: %r → %s", output_path, exc)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if len(payload) > config.MAX_UPLOAD_BYTES:
        _log.warning(
            "output too large to stage: %d bytes > %d cap",
            len(payload), config.MAX_UPLOAD_BYTES,
        )
        raise HTTPException(
            status_code=413,
            detail=(
                f"output too large to stage ({len(payload)} bytes > "
                f"{config.MAX_UPLOAD_BYTES})"
            ),
        )
    files_mod.write_atomic(dest, payload)
    _log.info("staged output: path=%s size=%d", rel, len(payload))
    body: dict = {"path": str(rel), "size": len(payload)}
    if extra_json:
        body.update(extra_json)
    return JSONResponse(body, status_code=200)


async def _write_url(
    payload: bytes,
    *,
    output_url: str,
    media_type: str,
    extra_json: dict | None,
) -> JSONResponse:
    try:
        await fetch.upload_bytes(output_url, payload, media_type)
    except fetch.FetchError as exc:
        _log.warning(
            "output_url upload failed: url=%s size=%d err=%s",
            output_url, len(payload), exc,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    _log.info(
        "uploaded output to url: size=%d media_type=%s",
        len(payload), media_type,
    )
    body: dict = {"url": output_url, "size": len(payload)}
    if extra_json:
        body.update(extra_json)
    return JSONResponse(body, status_code=200)
