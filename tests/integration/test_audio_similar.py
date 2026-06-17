"""End-to-end tests for ``POST /v1/audio/similar``.

Pairwise audio similarity via CLAP embeddings. JSON-only response with
similarity + dim. Needs primary + reference file paths.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = [
    pytest.mark.engine("clap-embed"),
    pytest.mark.hf_gated,
]


def test_similar_returns_score_in_range(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """Two distinct files → numeric similarity in [-1, 1]."""
    r = client.post(
        "/v1/audio/similar",
        json={
            "file_path": staged_audio,
            "reference_file_path": staged_reference,
        },
    )
    assert r.status_code == 200, r.text
    sim = r.json().get("similarity")
    assert isinstance(sim, (int, float))
    assert -1.0 <= sim <= 1.0


def test_similar_self_is_high(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Same file vs itself → similarity > 0.9."""
    r = client.post(
        "/v1/audio/similar",
        json={
            "file_path": staged_audio,
            "reference_file_path": staged_audio,
        },
    )
    assert r.status_code == 200, r.text
    sim = r.json()["similarity"]
    assert sim > 0.9, f"self-similarity {sim:.4f} not > 0.9"


def test_similar_dim_field(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """Response includes a non-zero dim field."""
    r = client.post(
        "/v1/audio/similar",
        json={
            "file_path": staged_audio,
            "reference_file_path": staged_reference,
        },
    )
    assert r.status_code == 200, r.text
    dim = r.json().get("dim")
    assert dim, f"missing/zero dim: {r.json()}"


def test_similar_missing_reference(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing reference_file_path → 400 or 422."""
    r = client.post("/v1/audio/similar", json={"file_path": staged_audio})
    assert r.status_code in (400, 422), r.text


def test_similar_missing_primary(
    client: httpx.Client, staged_reference: str,
) -> None:
    """Primary file_path does not exist → 4xx (or 500 from resolve)."""
    r = client.post(
        "/v1/audio/similar",
        json={
            "file_path": "no/such.wav",
            "reference_file_path": staged_reference,
        },
    )
    assert r.status_code in (400, 404, 422, 500), r.text


def test_similar_accepts_file_path_b_alias(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """`file_path_b` works as an alias for `reference_file_path` — the
    "compare two files" reading is more intuitive than primary +
    reference framing for a similarity check."""
    r = client.post(
        "/v1/audio/similar",
        json={
            "file_path": staged_audio,
            "file_path_b": staged_reference,
        },
        timeout=120.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert "similarity" in body
    assert isinstance(body["similarity"], (int, float))
