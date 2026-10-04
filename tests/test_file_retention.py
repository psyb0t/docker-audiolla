from __future__ import annotations

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

from audiolla.file_retention import FileRetention, FileRetentionMiddleware


def stage(path: Path, age: float = 100) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"audio")
    stamp = time.time() - age
    os.utime(path, (stamp, stamp))
    return path


@pytest.mark.asyncio
async def test_expired_only_and_idempotent(tmp_path):
    files = tmp_path / "files"
    old = stage(files / "nested" / "音.wav")
    recent = stage(files / "recent.wav", 1)
    future = stage(files / "future.wav", -100)
    partial = stage(files / "unfinished.part")
    model = stage(tmp_path / "models" / "model.bin")
    retention = FileRetention(files)
    assert await retention.sweep(50) == 1
    assert not old.exists()
    assert all(p.exists() for p in (recent, future, partial, model))
    assert await retention.sweep(50) == 0


@pytest.mark.asyncio
async def test_disabled_and_empty(tmp_path):
    files = tmp_path / "files"
    retention = FileRetention(files)
    assert await retention.sweep(1) == 0
    old = stage(files / "old.wav")
    assert await retention.sweep(0) == 0
    assert old.exists()


@pytest.mark.asyncio
async def test_exact_boundary(tmp_path, monkeypatch):
    old = stage(tmp_path / "files" / "old.wav")
    stamp = old.stat().st_mtime
    monkeypatch.setattr("audiolla.file_retention.time.time", lambda: stamp + 50)
    assert await FileRetention(old.parent).sweep(50) == 1


@pytest.mark.asyncio
async def test_symlinks_never_followed(tmp_path):
    outside = stage(tmp_path / "outside" / "keep.wav")
    files = tmp_path / "files"
    files.mkdir()
    (files / "linked.wav").symlink_to(outside)
    (files / "linked-dir").symlink_to(outside.parent, target_is_directory=True)
    assert await FileRetention(files).sweep(1) == 0
    assert outside.exists()
    root_link = tmp_path / "root-link"
    root_link.symlink_to(outside.parent, target_is_directory=True)
    assert await FileRetention(root_link).sweep(1) == 0
    assert outside.exists()


@pytest.mark.asyncio
async def test_shared_leases_across_instances(tmp_path):
    old = stage(tmp_path / "files" / "old.wav")
    first = FileRetention(old.parent)
    second = FileRetention(old.parent)
    lease = await first.acquire()
    other = await second.acquire()
    assert await second.sweep(1) is None
    lease.close()
    assert await first.sweep(1) is None
    other.close()
    other.close()
    assert await second.sweep(1) == 1


@pytest.mark.asyncio
async def test_other_process_postpones_sweep(tmp_path):
    old = stage(tmp_path / "files" / "old.wav")
    retention = FileRetention(old.parent)
    # A distinct process models the second container sharing /data.
    program = """
import asyncio, sys
from pathlib import Path
from audiolla.file_retention import FileRetention
lease = asyncio.run(FileRetention(Path(sys.argv[1])).acquire())
print('locked', flush=True)
sys.stdin.readline()
lease.close()
"""
    process = subprocess.Popen(
        [sys.executable, "-c", program, str(old.parent)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
    )
    try:
        assert process.stdout.readline().strip() == "locked"
        assert await retention.sweep(1) is None
    finally:
        process.communicate("release\n", timeout=10)
    assert process.returncode == 0
    assert await retention.sweep(1) == 1


@pytest.mark.asyncio
async def test_middleware_holds_until_response_finishes(tmp_path):
    old = stage(tmp_path / "files" / "old.wav")
    retention = FileRetention(old.parent)
    finish = asyncio.Event()
    started = asyncio.Event()

    async def endpoint(scope, receive, send):
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"audio", "more_body": True})
        started.set()
        await finish.wait()
        await send({"type": "http.response.body", "body": b"", "more_body": False})

    async def send(message):
        pass

    middleware = FileRetentionMiddleware(endpoint, retention=lambda: retention)
    task = asyncio.create_task(
        middleware(
            {"type": "http", "path": "/v1/files/old.wav", "method": "GET"},
            None,
            send,
        )
    )
    await started.wait()
    assert await retention.sweep(1) is None
    finish.set()
    await task
    assert await retention.sweep(1) == 1


@pytest.mark.asyncio
async def test_cancelled_request_releases(tmp_path):
    old = stage(tmp_path / "files" / "old.wav")
    retention = FileRetention(old.parent)
    started = asyncio.Event()

    async def endpoint(scope, receive, send):
        started.set()
        await asyncio.Event().wait()

    middleware = FileRetentionMiddleware(endpoint, retention=lambda: retention)
    task = asyncio.create_task(
        middleware(
            {"type": "http", "path": "/v1/audio/enhance", "method": "POST"},
            None,
            None,
        )
    )
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert await retention.sweep(1) == 1


@pytest.mark.asyncio
async def test_lock_symlink_fails_closed(tmp_path):
    old = stage(tmp_path / "files" / "old.wav")
    outside = stage(tmp_path / "outside")
    (tmp_path / ".files-cleanup.lock").symlink_to(outside)
    retention = FileRetention(old.parent)
    with pytest.raises(OSError):
        await retention.acquire()
    with pytest.raises(OSError):
        await retention.sweep(1)
    assert old.exists() and outside.read_bytes() == b"audio"


@pytest.mark.asyncio
async def test_permission_error_does_not_stop_other_deletes(tmp_path, caplog):
    blocked = stage(tmp_path / "files" / "blocked" / "old.wav")
    removed = stage(tmp_path / "files" / "old.wav")
    blocked.parent.chmod(0o500)
    try:
        assert await FileRetention(removed.parent).sweep(1) == 1
        assert blocked.exists() and not removed.exists()
        assert "file retention removal failed" in caplog.text
    finally:
        blocked.parent.chmod(0o700)


@pytest.mark.asyncio
@pytest.mark.parametrize("ttl", [-1, float("nan"), float("inf")])
async def test_invalid_sweep_ttl(tmp_path, ttl):
    with pytest.raises(ValueError, match="finite and nonnegative"):
        await FileRetention(tmp_path / "files").sweep(ttl)
