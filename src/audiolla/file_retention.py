"""Coordinate staged-file retention across containers sharing a data directory."""

from __future__ import annotations

import asyncio
import fcntl
import logging
import math
import os
import stat
import time
from collections.abc import Callable
from pathlib import Path

from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger(__name__)
LOCK_FILENAME = ".files-cleanup.lock"
LOCK_RETRY_SECONDS = 0.05
PARTIAL_SUFFIX = ".part"


class FileLease:
    def __init__(self, descriptor: int) -> None:
        self._descriptor: int | None = descriptor

    def close(self) -> None:
        if self._descriptor is None:
            return
        descriptor, self._descriptor = self._descriptor, None
        os.close(descriptor)


class FileRetention:
    def __init__(self, files_dir: Path) -> None:
        self.files_dir = files_dir

    def _open_lock(self) -> int:
        self.files_dir.parent.mkdir(parents=True, exist_ok=True)
        return os.open(
            self.files_dir.parent / LOCK_FILENAME,
            os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC,
            0o600,
        )

    async def acquire(self) -> FileLease:
        descriptor = self._open_lock()
        try:
            while True:
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_SH | fcntl.LOCK_NB)
                    return FileLease(descriptor)
                except BlockingIOError:
                    await asyncio.sleep(LOCK_RETRY_SECONDS)
        except BaseException:
            # Cancellation during lock acquisition must not leak a descriptor.
            os.close(descriptor)
            raise

    async def sweep(self, ttl_seconds: float) -> int | None:
        if not math.isfinite(ttl_seconds) or ttl_seconds < 0:
            raise ValueError("file retention TTL must be finite and nonnegative")
        if ttl_seconds == 0:
            return 0
        # The worker owns its lock until all deletes finish, even if cancelled.
        return await asyncio.to_thread(self._sweep, ttl_seconds)

    def _sweep(self, ttl_seconds: float) -> int | None:
        descriptor = self._open_lock()
        try:
            try:
                fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                log.debug("file retention postponed: active request or job")
                return None
            if self.files_dir.is_symlink() or not self.files_dir.exists():
                return 0
            cutoff = time.time() - ttl_seconds
            removed = 0
            failed = 0

            def walk_error(error: OSError) -> None:
                nonlocal failed
                failed += 1
                log.warning("file retention directory scan failed", exc_info=error)

            for _, _, names, directory in os.fwalk(
                self.files_dir, follow_symlinks=False, onerror=walk_error
            ):
                for name in names:
                    if name.endswith(PARTIAL_SUFFIX):
                        continue
                    try:
                        info = os.stat(name, dir_fd=directory, follow_symlinks=False)
                        if not stat.S_ISREG(info.st_mode) or info.st_mtime > cutoff:
                            continue
                        os.unlink(name, dir_fd=directory)
                        removed += 1
                    except FileNotFoundError:
                        continue
                    except OSError as error:
                        failed += 1
                        log.warning("file retention removal failed", exc_info=error)
            if removed or failed:
                log.info("file retention: removed=%d failed=%d", removed, failed)
            return removed
        finally:
            os.close(descriptor)


class FileRetentionMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        *,
        retention: Callable[[], FileRetention],
    ) -> None:
        self.app = app
        self.retention = retention

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        path = scope.get("path", "")
        is_mcp_stream = path.rstrip("/") == "/v1/mcp" and scope.get("method") == "GET"
        if scope["type"] != "http" or not path.startswith("/v1/") or is_mcp_stream:
            await self.app(scope, receive, send)
            return
        lease = await self.retention().acquire()
        try:
            await self.app(scope, receive, send)
        finally:
            lease.close()
