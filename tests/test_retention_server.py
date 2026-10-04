from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import httpx
import pytest

from audiolla import server
from audiolla.file_retention import FileRetention
from audiolla.jobs import JobQueue


def old_file(tmp_path: Path) -> Path:
    path = tmp_path / "files" / "old.wav"
    path.parent.mkdir()
    path.write_bytes(b"audio")
    stamp = time.time() - 100
    os.utime(path, (stamp, stamp))
    return path


@pytest.mark.asyncio
@pytest.mark.parametrize("outcome", ["success", "failure", "cancel", "queued-cancel"])
async def test_job_lease_until_terminal(tmp_path, outcome):
    path = old_file(tmp_path)
    retention = FileRetention(path.parent)
    lease = await retention.acquire()
    queue = JobQueue()
    started = asyncio.Event()
    finish = asyncio.Event()

    async def work():
        started.set()
        await finish.wait()
        if outcome == "failure":
            raise ValueError("test job failure")
        return {"ok": True}

    job = await queue.submit(work, endpoint="test", on_done=lease.close)
    if outcome == "queued-cancel":
        await queue.cancel(job.id)
    else:
        assert await retention.sweep(1) is None
        await started.wait()
        assert await retention.sweep(1) is None
        if outcome == "cancel":
            await queue.cancel(job.id)
        else:
            finish.set()
    await asyncio.gather(job._task, return_exceptions=True)
    await asyncio.sleep(0)
    assert await retention.sweep(1) == 1


@pytest.mark.asyncio
async def test_real_router_download_and_eventual_lifespan_cleanup(
    tmp_path, monkeypatch
):
    path = old_file(tmp_path)
    monkeypatch.setattr(server.config, "FILES_DIR", path.parent)
    monkeypatch.setattr(server.config, "FILES_TTL_SECONDS", 50)
    monkeypatch.setattr(server.config, "SWEEPER_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(server.config, "PRELOAD", [])
    monkeypatch.setattr(server, "ENGINES", {})
    async with server.app.router.lifespan_context(server.app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=server.app), base_url="http://test"
        ) as client:
            response = await client.get("/v1/files/old.wav")
            assert response.status_code == 200
            assert response.content == b"audio"
            for _ in range(200):
                if not path.exists():
                    break
                await asyncio.sleep(0.01)
            assert not path.exists()
            assert (await client.get("/v1/files/old.wav")).status_code == 404
            assert (await client.get("/healthz")).status_code == 200
    assert server._file_sweeper_task.done()


@pytest.mark.asyncio
async def test_submit_job_protects_after_202(tmp_path, monkeypatch):
    path = old_file(tmp_path)
    monkeypatch.setattr(server.config, "FILES_DIR", path.parent)
    queue = JobQueue()
    monkeypatch.setattr(server, "JOB_QUEUE", queue)
    finish = asyncio.Event()

    async def response():
        await finish.wait()
        return server.JSONResponse({"ok": True})

    result = await server._submit_job(
        response(), endpoint="test", webhook_url=None, job_id="test-job"
    )
    assert result.status_code == 202
    retention = FileRetention(path.parent)
    assert await retention.sweep(1) is None
    finish.set()
    job = await queue.get("test-job")
    await job._task
    await asyncio.sleep(0)
    assert await retention.sweep(1) == 1
