"""End-to-end tests for ``POST /v1/audio/chords``.

Chord + key estimation via chordino / librosa. JSON-only response with
key (string) + chords array.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.engine("chord-detect")


def test_chords_returns_key_and_chords(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response has a non-empty key string + chords array."""
    r = client.post("/v1/audio/chords", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["key"], str)
    assert len(body["key"]) > 0
    assert isinstance(body["chords"], list)


def test_chords_rejects_missing_file(client: httpx.Client) -> None:
    """No input → 4xx."""
    r = client.post("/v1/audio/chords")
    assert 400 <= r.status_code < 500, r.text


def test_chords_custom_hop_length(
    client: httpx.Client, staged_audio: str,
) -> None:
    """hop_length=1024 still produces a key."""
    r = client.post(
        "/v1/audio/chords",
        json={"file_path": staged_audio, "hop_length": 1024},
    )
    assert r.status_code == 200, r.text
    assert isinstance(r.json()["key"], str)


def test_chords_segment_min_duration_sec(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Larger min duration produces no more segments than a small one."""
    short = client.post(
        "/v1/audio/chords",
        json={"file_path": staged_audio, "segment_min_duration_sec": 0.1},
    )
    long_ = client.post(
        "/v1/audio/chords",
        json={"file_path": staged_audio, "segment_min_duration_sec": 2.0},
    )
    assert short.status_code == 200 and long_.status_code == 200
    n_short = len(short.json()["chords"])
    n_long = len(long_.json()["chords"])
    assert n_long <= n_short, (
        f"larger min_duration produced MORE segments ({n_short} vs {n_long})"
    )
