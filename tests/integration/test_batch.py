"""End-to-end tests for ``POST /v1/batch``.

Body is a JSON array of operation objects; each runs sequentially and
returns a per-op result with status / error. Per-op failures do NOT fail
the request — they surface as `error` entries.
"""

from __future__ import annotations

import secrets

import httpx
import pytest

pytestmark = pytest.mark.engine("librosa-analyze")


@pytest.fixture
def staged_for_batch(client: httpx.Client, staged_audio: str) -> str:
    """Convert the staged audio into a known path under ``batch_e2e/``.

    Mirrors the bash setup_staged_input — guarantees the input lives where
    each test's `file_path` parameter expects it. Unique per test to keep
    parallel runs collision-free.
    """
    dest = f"batch_e2e/input-{secrets.token_hex(4)}.wav"
    r = client.post(
        "/v1/audio/convert",
        json={"file_path": staged_audio, "output_path": dest},
    )
    assert r.status_code == 200, r.text
    return dest


def test_batch_single_trim(
    client: httpx.Client, staged_for_batch: str,
) -> None:
    """Single trim op returns a results array of length 1, status=ok."""
    out = f"batch_e2e/trim-{secrets.token_hex(4)}.wav"
    r = client.post(
        "/v1/batch",
        json=[{
            "op": "trim",
            "file_path": staged_for_batch,
            "output_path": out,
            "start_sec": 0,
            "end_sec": 2,
        }],
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["results"], list)
    first = body["results"][0]
    assert first["status"] == "ok"
    assert first["path"] == out


def test_batch_multi_ops(
    client: httpx.Client, staged_for_batch: str,
) -> None:
    """3 mixed ops all succeed in one call."""
    tag = secrets.token_hex(4)
    r = client.post(
        "/v1/batch",
        json=[
            {
                "op": "trim",
                "file_path": staged_for_batch,
                "output_path": f"batch_e2e/trim-{tag}.wav",
                "start_sec": 0,
                "end_sec": 3,
            },
            {
                "op": "convert",
                "file_path": staged_for_batch,
                "output_path": f"batch_e2e/conv-{tag}.mp3",
                "output_format": "mp3",
            },
            {
                "op": "reverse",
                "file_path": staged_for_batch,
                "output_path": f"batch_e2e/rev-{tag}.wav",
            },
        ],
    )
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert len(results) == 3
    bad = [res for res in results if res.get("status") != "ok"]
    assert not bad, f"some ops failed: {bad}"


def test_batch_unsupported_op_error_in_results(
    client: httpx.Client, staged_for_batch: str,
) -> None:
    """Unsupported op → HTTP 200 with an error entry on that index."""
    r = client.post(
        "/v1/batch",
        json=[{
            "op": "nonexistent_op",
            "file_path": staged_for_batch,
        }],
    )
    assert r.status_code == 200, r.text
    results = r.json()["results"]
    assert results[0].get("error") is not None


def test_batch_invalid_json_400(client: httpx.Client) -> None:
    """Non-JSON body → 400."""
    r = client.post(
        "/v1/batch",
        content=b"not json",
        headers={"Content-Type": "application/json"},
    )
    assert r.status_code == 400, r.text


def test_batch_non_array_body_400(client: httpx.Client) -> None:
    """Body that isn't a JSON array → 400."""
    r = client.post("/v1/batch", json={"op": "trim"})
    assert r.status_code == 400, r.text


def test_batch_nonexistent_file_path(client: httpx.Client) -> None:
    """Bad file_path → per-op error entry (not request-level failure)."""
    r = client.post(
        "/v1/batch",
        json=[{
            "op": "trim",
            "file_path": "batch_e2e/nonexistent.wav",
            "start_sec": 0,
            "end_sec": 1,
        }],
    )
    assert r.status_code == 200, r.text
    assert r.json()["results"][0].get("error") is not None
