from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path

import httpx
import pytest

from audiolla import server
from audiolla.engines.base import EngineBase
from audiolla.engine_workers import WorkerEngine
from audiolla.file_retention import FileRetention
from audiolla.jobs import JobQueue
from audiolla.model_process import ModelProcess


class BlockingModel:
    def __init__(self, root: Path) -> None:
        self.root = root

    async def execute(self, operation: str) -> int:
        assert operation == "get_model"
        (self.root / "worker-started").touch()
        deadline = time.monotonic() + 5
        while not (self.root / "worker-release").exists():
            if time.monotonic() >= deadline:
                raise TimeoutError("worker test was not released")
            await asyncio.sleep(0.01)
        return os.getpid()

    def resident(self) -> bool:
        return True

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_bulk_unload_waits_for_no_inference_and_reaps_worker(tmp_path, monkeypatch):
    engine = WorkerEngine(EngineBase("fixture", {}), "cpu", server._workers)
    engine._process = ModelProcess(BlockingModel, tmp_path)
    monkeypatch.setattr(server, "ENGINES", {"fixture": engine})
    monkeypatch.setattr(server.config, "FILES_DIR", tmp_path / "files")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=server.app), base_url="http://test"
    ) as client:
        assert (await client.post("/v1/unload")).json() == {"unloaded": []}
        task = asyncio.create_task(engine.get_model())
        try:
            for _ in range(500):
                if (tmp_path / "worker-started").exists():
                    break
                await asyncio.sleep(0.01)
            assert (tmp_path / "worker-started").exists()
            assert (await client.post("/v1/unload")).status_code == 409
        finally:
            (tmp_path / "worker-release").touch()
            pid = await task
        try:
            assert pid != os.getpid()
            assert (await client.post("/v1/unload")).json() == {"unloaded": ["fixture"]}
            with pytest.raises(ProcessLookupError):
                os.kill(pid, 0)
            assert (await client.post("/v1/unload")).json() == {"unloaded": []}
        finally:
            await engine.close()


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
