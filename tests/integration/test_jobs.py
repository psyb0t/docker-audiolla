"""End-to-end tests for the async job queue.

Submission via ``async_job=true`` on any audio endpoint, polling via
``GET /v1/jobs/{id}``, listing via ``GET /v1/jobs``, cancellation via
``DELETE /v1/jobs/{id}``.

Uses ``POST /v1/audio/visualize/image/waveform`` as the submitting
endpoint — ffmpeg-render is fast on the synthetic fixture and the result
type (PNG) is easy to verify if needed.
"""

from __future__ import annotations

import secrets
import time

import httpx
import pytest

pytestmark = pytest.mark.engine("ffmpeg-render")


def _poll_job(
    client: httpx.Client, job_id: str, *, timeout: float = 30.0,
) -> dict:
    """Poll until the job is in a terminal state or the timeout fires."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        r = client.get(f"/v1/jobs/{job_id}")
        assert r.status_code == 200, r.text
        body = r.json()
        if body["status"] in ("completed", "failed", "cancelled"):
            return body
        time.sleep(0.5)
    raise AssertionError(f"job {job_id} did not finish in {timeout}s")


def test_async_job_submit_and_poll(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Submitting async_job=true returns a job_id; polling reaches completed."""
    submit = client.post(
        "/v1/audio/visualize/image/waveform",
        json={
            "file_path": staged_audio,
            "async_job": True,
            "output_path": f"jobs/wave-{secrets.token_hex(4)}.png",
        },
    )
    assert submit.status_code in (200, 202), submit.text
    submit_body = submit.json()
    job_id = submit_body["job_id"]
    assert job_id
    assert submit_body["status"] in ("pending", "running")

    final = _poll_job(client, job_id, timeout=30.0)
    assert final["status"] == "completed", final
    assert final["result"] is not None
    assert isinstance(final["duration_sec"], (int, float))


def test_jobs_list_returns_array(client: httpx.Client) -> None:
    """GET /v1/jobs always returns a jobs array (possibly empty)."""
    r = client.get("/v1/jobs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["jobs"], list)


def test_jobs_list_filter_by_status(
    client: httpx.Client, staged_audio: str,
) -> None:
    """?status=completed only returns jobs with that status."""
    # Force at least one completed job to exist by submitting + polling.
    submit = client.post(
        "/v1/audio/visualize/image/waveform",
        json={
            "file_path": staged_audio,
            "async_job": True,
            "output_path": f"jobs/wave-{secrets.token_hex(4)}.png",
        },
    )
    job_id = submit.json()["job_id"]
    _poll_job(client, job_id, timeout=30.0)

    r = client.get("/v1/jobs", params={"status": "completed"})
    assert r.status_code == 200, r.text
    jobs = r.json()["jobs"]
    for job in jobs:
        assert job["status"] == "completed"


def test_job_not_found_404(client: httpx.Client) -> None:
    """GET unknown job ID → 404."""
    r = client.get("/v1/jobs/00000000-0000-0000-0000-000000000000")
    assert r.status_code == 404, r.text


def test_async_job_cancel(
    client: httpx.Client, staged_audio: str,
) -> None:
    """DELETE on a submitted job → status becomes cancelled or completed."""
    submit = client.post(
        "/v1/audio/visualize/image/waveform",
        json={
            "file_path": staged_audio,
            "async_job": True,
            "output_path": f"jobs/cancel-{secrets.token_hex(4)}.png",
        },
    )
    job_id = submit.json()["job_id"]
    cancel = client.delete(f"/v1/jobs/{job_id}")
    assert cancel.status_code == 200, cancel.text
    cancel_body = cancel.json()
    assert cancel_body["job_id"] == job_id

    # Give it a moment, then verify final status. Fast jobs may complete
    # before the cancel reaches the worker — both are acceptable.
    time.sleep(1.0)
    follow = client.get(f"/v1/jobs/{job_id}")
    if follow.status_code == 200:
        assert follow.json()["status"] in ("cancelled", "completed")
    else:
        # DELETE on a terminal job removes it → 404 is fine here.
        assert follow.status_code == 404


def test_delete_job_not_found_404(client: httpx.Client) -> None:
    """DELETE on unknown job ID → 404."""
    r = client.delete("/v1/jobs/00000000-0000-0000-0000-000000000001")
    assert r.status_code == 404, r.text
