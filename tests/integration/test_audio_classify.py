"""End-to-end tests for ``POST /v1/audio/classify``.

Zero-shot audio classification via CLAP. Caller provides a labels array;
response is a results array of {label, score} sorted by descending score.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = [
    pytest.mark.engine("clap-embed"),
    pytest.mark.hf_gated,
]

_LABELS = ["sine wave", "music", "speech", "silence", "noise"]


def test_classify_returns_results(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response contains a results array."""
    r = client.post(
        "/v1/audio/classify",
        json={"file_path": staged_audio, "labels": _LABELS},
    )
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["results"], list)


def test_classify_result_count_matches_labels(
    client: httpx.Client, staged_audio: str,
) -> None:
    """One result per supplied label."""
    r = client.post(
        "/v1/audio/classify",
        json={"file_path": staged_audio, "labels": _LABELS},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["results"]) == len(_LABELS)


def test_classify_result_schema(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Each entry has a string label + numeric score."""
    r = client.post(
        "/v1/audio/classify",
        json={"file_path": staged_audio, "labels": _LABELS},
    )
    assert r.status_code == 200, r.text
    for res in r.json()["results"]:
        assert isinstance(res["label"], str)
        assert isinstance(res["score"], (int, float))


def test_classify_sorted_descending(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Results are sorted by score descending."""
    r = client.post(
        "/v1/audio/classify",
        json={"file_path": staged_audio, "labels": _LABELS},
    )
    assert r.status_code == 200, r.text
    scores = [res["score"] for res in r.json()["results"]]
    assert scores == sorted(scores, reverse=True), scores


def test_classify_single_label(
    client: httpx.Client, staged_audio: str,
) -> None:
    """A single label → exactly one result."""
    r = client.post(
        "/v1/audio/classify",
        json={"file_path": staged_audio, "labels": ["music"]},
    )
    assert r.status_code == 200, r.text
    assert len(r.json()["results"]) == 1


def test_classify_missing_labels_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing labels → 422 (required field)."""
    r = client.post("/v1/audio/classify", json={"file_path": staged_audio})
    assert r.status_code == 422, r.text


def test_classify_labels_wrong_type_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """labels is a string instead of array → 422."""
    r = client.post(
        "/v1/audio/classify",
        json={"file_path": staged_audio, "labels": "not-json"},
    )
    assert r.status_code == 422, r.text


def test_classify_empty_labels_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Empty labels array → 400."""
    r = client.post(
        "/v1/audio/classify",
        json={"file_path": staged_audio, "labels": []},
    )
    assert r.status_code == 400, r.text


def test_classify_missing_file_404(client: httpx.Client) -> None:
    """Nonexistent staged file path → 404."""
    r = client.post(
        "/v1/audio/classify",
        json={"file_path": "no/such.wav", "labels": _LABELS},
    )
    assert r.status_code == 404, r.text
