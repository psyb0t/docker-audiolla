"""End-to-end tests for ``POST /v1/audio/tag``.

Audio Spectrogram Transformer (AST) audio event tagging. Returns sorted
list of (label, score) tags + duration. Requires the AST model (~90 MB)
cached in HF_HOME.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = [
    pytest.mark.engine("ast-tag"),
    pytest.mark.hf_gated,
]


def test_tag_returns_tags_and_duration(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries a non-empty tags array with label+score, plus duration."""
    r = client.post("/v1/audio/tag", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["tags"], list)
    assert len(body["tags"]) > 0
    first = body["tags"][0]
    assert "label" in first
    assert "score" in first
    assert isinstance(body["duration"], (int, float))
    assert body["duration"] > 0


def test_tag_rejects_missing_file(client: httpx.Client) -> None:
    """No input → 4xx."""
    r = client.post("/v1/audio/tag")
    assert 400 <= r.status_code < 500, r.text


def test_tag_top_k(client: httpx.Client, staged_audio: str) -> None:
    """top_k=5 caps the response to ≤5 tags."""
    r = client.post(
        "/v1/audio/tag",
        json={"file_path": staged_audio, "top_k": 5},
    )
    assert r.status_code == 200, r.text
    tags = r.json()["tags"]
    assert isinstance(tags, list)
    assert len(tags) <= 5


def test_tag_score_range(client: httpx.Client, staged_audio: str) -> None:
    """Every tag score is in [0, 1]."""
    r = client.post("/v1/audio/tag", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    for t in r.json()["tags"]:
        assert 0.0 <= t["score"] <= 1.0, t
