"""End-to-end tests for ``POST /v1/audio/loudness/curve``.

RMS-envelope-over-time analysis. JSON-only response with curve points,
each carrying time_sec + rms_db.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.engine("librosa-analyze")


def test_loudness_curve_shape(client: httpx.Client, staged_audio: str) -> None:
    """Response has curve (array), duration (>0), points (>0)."""
    r = client.post("/v1/audio/loudness/curve", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["curve"], list)
    assert body["duration"] > 0
    assert body["points"] > 0


def test_loudness_curve_entry_fields(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Every curve entry carries numeric time_sec + rms_db."""
    r = client.post("/v1/audio/loudness/curve", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    first = body["curve"][0]
    assert isinstance(first["time_sec"], (int, float))
    assert isinstance(first["rms_db"], (int, float))


def test_loudness_curve_file_path_roundtrip(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Convert → re-stage → curve still works on the staged copy."""
    conv = client.post(
        "/v1/audio/convert",
        json={"file_path": staged_audio, "output_path": "lc_test/audio.wav"},
    )
    assert conv.status_code == 200, conv.text

    r = client.post(
        "/v1/audio/loudness/curve",
        json={"file_path": "lc_test/audio.wav"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["curve"]) > 0


def test_loudness_curve_custom_hop(
    client: httpx.Client, staged_audio: str,
) -> None:
    """hop_length=1024 is reflected back in the response."""
    r = client.post(
        "/v1/audio/loudness/curve",
        json={"file_path": staged_audio, "hop_length": 1024},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["hop_length"] == 1024
