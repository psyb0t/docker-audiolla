"""End-to-end tests for ``POST /v1/audio/analyze``.

Librosa MIR feature extraction — bpm, key, loudness, duration, spectral
centroid, RMS, zero-crossing rate. Returns JSON only (no output_path).
"""

from __future__ import annotations

import secrets

import httpx
import pytest

pytestmark = pytest.mark.engine("librosa-analyze")


def test_analyze_all_features(client: httpx.Client, staged_audio: str) -> None:
    """Explicit feature list returns every requested key with sane values."""
    r = client.post(
        "/v1/audio/analyze",
        json={
            "file_path": staged_audio,
            "features": [
                "bpm",
                "key",
                "loudness",
                "duration",
                "spectral_centroid",
                "rms",
                "zcr",
            ],
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    for key in (
        "duration",
        "bpm",
        "key",
        "loudness_lufs",
        "spectral_centroid",
        "rms",
        "zcr",
    ):
        assert body.get(key) is not None, f"missing {key}: {body}"
    assert 1.0 <= body["duration"] <= 120.0
    assert -70.0 <= body["loudness_lufs"] <= 0.0


def test_analyze_default_features(client: httpx.Client, staged_audio: str) -> None:
    """No features list → all features returned by default."""
    r = client.post("/v1/audio/analyze", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("duration") is not None


def test_analyze_unknown_feature_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Unknown feature name → 400."""
    r = client.post(
        "/v1/audio/analyze",
        json={"file_path": staged_audio, "features": ["not-a-feature"]},
    )
    assert r.status_code == 400, r.text


def test_analyze_bad_input_400(client: httpx.Client) -> None:
    """Non-audio bytes → 400 from the conversion layer."""
    rel = f"uploads/junk-{secrets.token_hex(8)}.txt"
    put = client.put(
        f"/v1/files/{rel}",
        content=b"this is not audio",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert put.status_code in (200, 201)

    r = client.post("/v1/audio/analyze", json={"file_path": rel})
    assert r.status_code == 400, r.text
