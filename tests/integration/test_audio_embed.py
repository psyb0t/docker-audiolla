"""End-to-end tests for ``POST /v1/audio/embed``.

CLAP audio embedding — 512-dim L2-normalised vector + optional text
similarity score. Requires the CLAP model (~250 MB) cached in HF_HOME.
"""

from __future__ import annotations

import math

import httpx
import pytest

pytestmark = [
    pytest.mark.engine("clap-embed"),
    pytest.mark.hf_gated,
]


def test_embed_returns_512d_embedding(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response contains a 512-element embedding array and dim=512."""
    r = client.post("/v1/audio/embed", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["embedding"], list)
    assert len(body["embedding"]) > 0
    assert body["dim"] == 512


def test_embed_l2_norm(client: httpx.Client, staged_audio: str) -> None:
    """The embedding is L2-normalised (norm ≈ 1.0)."""
    r = client.post("/v1/audio/embed", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    v = r.json()["embedding"]
    n = math.sqrt(sum(x * x for x in v))
    assert abs(n - 1.0) < 0.01, f"L2 norm {n:.4f} not ~1.0"


def test_embed_query_text_similarity(
    client: httpx.Client, staged_audio: str,
) -> None:
    """query_text returns a numeric similarity and echoes the text back."""
    r = client.post(
        "/v1/audio/embed",
        json={"file_path": staged_audio, "query_text": "sine wave tone"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["similarity"], (int, float))
    assert isinstance(body["query_text"], str)
    assert len(body["query_text"]) > 0


def test_embed_similarity_range(
    client: httpx.Client, staged_audio: str,
) -> None:
    """similarity is in [-1, 1]."""
    r = client.post(
        "/v1/audio/embed",
        json={"file_path": staged_audio, "query_text": "music"},
    )
    assert r.status_code == 200, r.text
    sim = r.json()["similarity"]
    assert -1.0 <= sim <= 1.0, f"similarity {sim} out of [-1, 1]"


def test_embed_rejects_missing_file(client: httpx.Client) -> None:
    """No input at all → 4xx."""
    r = client.post("/v1/audio/embed")
    assert 400 <= r.status_code < 500, r.text
