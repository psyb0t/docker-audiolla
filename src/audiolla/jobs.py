"""Async job queue for long-running audio-processing tasks.

Jobs are kept in memory for JOB_TTL_SECONDS (default 3600) after completion.
A sweeper in server.py calls cleanup() periodically.
"""

from __future__ import annotations

import asyncio
import enum
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable
import logging

_log = logging.getLogger("audiolla.jobs")


class JobStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


@dataclass
class Job:
    id: str
    endpoint: str
    status: JobStatus = JobStatus.pending
    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    completed_at: float | None = None
    result: dict | None = None
    error: str | None = None
    webhook_url: str | None = None
    _task: asyncio.Task | None = field(default=None, repr=False, compare=False)

    def to_dict(self) -> dict:
        d: dict[str, Any] = {
            "id": self.id,
            "endpoint": self.endpoint,
            "status": self.status.value,
            "created_at": self.created_at,
        }
        if self.started_at is not None:
            d["started_at"] = self.started_at
        if self.completed_at is not None:
            d["completed_at"] = self.completed_at
        if self.result is not None:
            d["result"] = self.result
        if self.error is not None:
            d["error"] = self.error
        if self.webhook_url is not None:
            d["webhook_url"] = self.webhook_url
        if self.status == JobStatus.completed and self.started_at and self.completed_at:
            d["duration_sec"] = round(self.completed_at - self.started_at, 3)
        return d


class JobQueue:
    def __init__(self) -> None:
        self._jobs: dict[str, Job] = {}

    @staticmethod
    def new_id() -> str:
        return str(uuid.uuid4())

    async def submit(
        self,
        coro_fn: Callable[[], Awaitable[Any]],
        *,
        job_id: str | None = None,
        endpoint: str,
        webhook_url: str | None = None,
    ) -> Job:
        jid = job_id or self.new_id()
        job = Job(id=jid, endpoint=endpoint, webhook_url=webhook_url)
        self._jobs[jid] = job
        job._task = asyncio.create_task(
            self._run(job, coro_fn), name=f"audiolla-job-{jid}"
        )
        return job

    async def _run(self, job: Job, coro_fn: Callable[[], Awaitable[Any]]) -> None:
        job.status = JobStatus.running
        job.started_at = time.time()
        _log.info("job %s started: endpoint=%s", job.id, job.endpoint)
        try:
            result = await coro_fn()
            job.result = result if isinstance(result, dict) else {"value": result}
            job.status = JobStatus.completed
        except asyncio.CancelledError:
            job.status = JobStatus.cancelled
            _log.warning("job %s cancelled (endpoint=%s)", job.id, job.endpoint)
            raise
        except Exception as exc:
            job.status = JobStatus.failed
            job.error = str(exc)
            _log.exception(
                "job %s failed (endpoint=%s): %s",
                job.id, job.endpoint, exc,
            )
        finally:
            job.completed_at = time.time()
            duration = (
                round(job.completed_at - job.started_at, 3)
                if job.started_at else 0.0
            )
            if job.status == JobStatus.completed:
                _log.info(
                    "job %s %s in %.3fs (endpoint=%s)",
                    job.id, job.status.value, duration, job.endpoint,
                )

        if job.status == JobStatus.completed and job.webhook_url:
            asyncio.create_task(
                self._fire_webhook(job), name=f"audiolla-webhook-{job.id}"
            )

    async def _fire_webhook(self, job: Job) -> None:
        url = job.webhook_url
        if not url:
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            return
        payload = job.to_dict()
        try:
            import httpx

            async with httpx.AsyncClient(timeout=10.0) as client:
                for attempt, delay in enumerate([0, 1, 2, 4]):
                    if attempt > 0:
                        await asyncio.sleep(delay)
                    try:
                        resp = await client.post(url, json=payload)
                        if resp.status_code < 500:
                            _log.info(
                                "webhook delivered for job %s (status=%d, attempt=%d)",
                                job.id, resp.status_code, attempt + 1,
                            )
                            return
                        _log.warning(
                            "webhook attempt %d for job %s got %d; retrying",
                            attempt + 1, job.id, resp.status_code,
                        )
                    except httpx.TransportError as exc:
                        _log.warning(
                            "webhook attempt %d for job %s failed: %s",
                            attempt + 1, job.id, exc,
                        )
                        if attempt == 3:
                            raise
        except Exception as exc:
            _log.warning(
                "webhook delivery for job %s gave up after retries: %s",
                job.id, exc,
            )

    async def cancel(self, job_id: str) -> bool:
        job = self._jobs.get(job_id)
        if job is None:
            return False
        task = job._task
        if task is None or task.done():
            return False
        task.cancel()
        return True

    async def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def list_jobs(self, *, status: str | None = None) -> list[dict]:
        jobs = list(self._jobs.values())
        if status is not None:
            try:
                filter_status = JobStatus(status)
            except ValueError:
                return []
            jobs = [j for j in jobs if j.status == filter_status]
        return [j.to_dict() for j in sorted(jobs, key=lambda j: j.created_at)]

    async def cleanup(self, ttl_seconds: float) -> int:
        now = time.time()
        terminal = {JobStatus.completed, JobStatus.failed, JobStatus.cancelled}
        to_delete = [
            jid
            for jid, job in self._jobs.items()
            if job.status in terminal
            and job.completed_at is not None
            and (now - job.completed_at) > ttl_seconds
        ]
        for jid in to_delete:
            del self._jobs[jid]
        return len(to_delete)


JOB_QUEUE = JobQueue()
