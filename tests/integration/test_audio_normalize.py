"""End-to-end test for ``POST /v1/audio/normalize``.

Loudness normalization via pyloudnorm. Targets a specific LUFS level.
Common targets: -14 (Spotify/YouTube), -16 (Apple Music), -23 (broadcast).
"""

from __future__ import annotations

import httpx

from .helpers import assert_wav


def test_normalize_returns_audio_and_measured_lufs(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Happy path: response carries measured_lufs; staged file is real WAV."""
    r = client.post(
        "/v1/audio/normalize",
        json={
            "file_path": staged_audio,
            "target_lufs": -14,
            "output_path": "out/normalize.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    # response may carry measured_lufs OR loudness_lufs
    lufs = body.get("measured_lufs", body.get("loudness_lufs"))
    assert lufs is not None, body

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_normalize_target_lufs_zero_boundary(
    client: httpx.Client, staged_audio: str,
) -> None:
    """target_lufs=-0.1 is the upper ceiling — still accepted."""
    r = client.post(
        "/v1/audio/normalize",
        json={
            "file_path": staged_audio,
            "target_lufs": -0.1,
            "output_path": "out/normalize_ceil.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_normalize_missing_file_404(client: httpx.Client) -> None:
    """file_path pointing to a non-staged file → 404."""
    r = client.post(
        "/v1/audio/normalize",
        json={
            "file_path": "ghost.wav",
            "target_lufs": -14,
            "output_path": "ghost-out.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_normalize_no_target_lufs_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing required `target_lufs` → Pydantic 422."""
    r = client.post(
        "/v1/audio/normalize",
        json={
            "file_path": staged_audio,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 422, r.text


def test_normalize_moves_loudness_toward_target(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Output LUFS is closer to target (within 1 dB slop) than the source."""
    target = -14

    before = client.post(
        "/v1/audio/loudness", json={"file_path": staged_audio},
    )
    assert before.status_code == 200
    before_lufs = float(before.json()["loudness_lufs"])

    r = client.post(
        "/v1/audio/normalize",
        json={
            "file_path": staged_audio,
            "target_lufs": target,
            "output_path": "normalize/out.wav",
        },
    )
    assert r.status_code == 200, r.text

    after = client.post(
        "/v1/audio/loudness", json={"file_path": "normalize/out.wav"},
    )
    assert after.status_code == 200
    after_lufs = float(after.json()["loudness_lufs"])

    assert abs(after_lufs - target) <= abs(before_lufs - target) + 1.0, (
        f"normalize didn't move loudness closer to target: "
        f"before={before_lufs} after={after_lufs} target={target}"
    )
