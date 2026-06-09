"""End-to-end tests for ``POST /v1/audio/loop-point``.

Loop-point detection — finds the best (start, end) pair for seamless
loops. JSON-only response with loop_start_sec, loop_end_sec, tempo_bpm,
duration, candidates, plus optional bars/score on real beat content.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.engine("librosa-analyze")


def test_loop_point_shape(client: httpx.Client, staged_audio: str) -> None:
    """Sine fixture (fallback path) → all required keys present."""
    r = client.post("/v1/audio/loop-point", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    for key in (
        "loop_start_sec",
        "loop_end_sec",
        "tempo_bpm",
        "duration",
        "candidates",
    ):
        assert key in body, f"missing {key}: {body}"
    assert isinstance(body["candidates"], list)


def test_loop_point_start_le_end(
    client: httpx.Client, staged_audio: str,
) -> None:
    """loop_start_sec <= loop_end_sec."""
    r = client.post("/v1/audio/loop-point", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["loop_start_sec"] <= body["loop_end_sec"]


def test_loop_point_beat_fixture_real_candidates(
    client: httpx.Client, staged_beat: str,
) -> None:
    """120-BPM click track → real loop detection (no fallback note), bars >= 1,
    score in [0, 1]."""
    r = client.post(
        "/v1/audio/loop-point",
        json={
            "file_path": staged_beat,
            "min_loop_bars": 1,
            "num_candidates": 3,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("note") is None, f"got fallback note: {body.get('note')}"
    assert body["bars"] >= 1
    assert 0.0 <= body["score"] <= 1.0


def test_loop_point_beat_fixture_loop_length(
    client: httpx.Client, staged_beat: str,
) -> None:
    """Detected loop on the click track is at least 1 second long."""
    r = client.post(
        "/v1/audio/loop-point",
        json={"file_path": staged_beat, "min_loop_bars": 1},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    length = body["loop_end_sec"] - body["loop_start_sec"]
    assert length >= 1.0, f"loop too short ({length}s)"


def test_loop_point_candidates_count(
    client: httpx.Client, staged_beat: str,
) -> None:
    """num_candidates is accepted; candidates array stays present."""
    r = client.post(
        "/v1/audio/loop-point",
        json={"file_path": staged_beat, "num_candidates": 3},
    )
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["candidates"], list)


def test_loop_point_invalid_bars(
    client: httpx.Client, staged_audio: str,
) -> None:
    """min_loop_bars=0 → 400 or 422."""
    r = client.post(
        "/v1/audio/loop-point",
        json={"file_path": staged_audio, "min_loop_bars": 0},
    )
    assert r.status_code in (400, 422), r.text
