"""End-to-end tests for ``POST /v1/audio/stereo-field``.

L/R correlation + width + balance + mono compatibility analysis.
JSON-only response — no output_path.
"""

from __future__ import annotations

import httpx


def test_stereo_field_shape(client: httpx.Client, staged_audio: str) -> None:
    """Response carries every documented field."""
    r = client.post("/v1/audio/stereo-field", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    for field in (
        "correlation",
        "width",
        "balance_db",
        "mono_compatible",
        "mid_level_db",
        "side_level_db",
        "phase_issues",
        "channels",
        "sample_rate",
        "duration",
    ):
        assert field in body, f"missing field {field!r}: {body}"


def test_stereo_field_correlation_range(
    client: httpx.Client, staged_audio: str,
) -> None:
    """correlation is in [-1, 1]."""
    r = client.post("/v1/audio/stereo-field", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    corr = r.json()["correlation"]
    assert -1.0 <= corr <= 1.0, f"correlation {corr} out of [-1,1]"


def test_stereo_field_sine_is_correlated(
    client: httpx.Client, staged_audio: str,
) -> None:
    """The L=R sine fixture has correlation ~1.0 and mono_compatible=true."""
    r = client.post("/v1/audio/stereo-field", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["correlation"] > 0.99, (
        f"L=R sine should have corr~1.0, got {body['correlation']}"
    )
    assert body["mono_compatible"] is True


def test_stereo_field_width_nonneg(
    client: httpx.Client, staged_audio: str,
) -> None:
    """width is >= 0."""
    r = client.post("/v1/audio/stereo-field", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    assert r.json()["width"] >= 0


def test_stereo_field_file_path_after_convert(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Convert → re-stage → stereo-field still produces a correlation."""
    conv = client.post(
        "/v1/audio/convert",
        json={
            "file_path": staged_audio,
            "output_path": "stereofield_test/in.wav",
        },
    )
    assert conv.status_code == 200, conv.text
    assert conv.json()["path"] == "stereofield_test/in.wav"

    r = client.post(
        "/v1/audio/stereo-field",
        json={"file_path": "stereofield_test/in.wav"},
    )
    assert r.status_code == 200, r.text
    assert "correlation" in r.json()
