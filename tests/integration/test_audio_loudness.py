"""End-to-end tests for ``POST /v1/audio/loudness`` (LUFS measurement)
plus a normalize round-trip via ``POST /v1/audio/normalize``.

Both endpoints use pyloudnorm directly — no engine declaration required.
"""

from __future__ import annotations

import secrets

import httpx

from .helpers import assert_wav


def test_loudness_analyze_only(client: httpx.Client, staged_audio: str) -> None:
    """No target_lufs → JSON {loudness_lufs, normalized: false}."""
    r = client.post("/v1/audio/loudness", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("loudness_lufs") is not None
    assert body.get("normalized") is False
    lufs = body["loudness_lufs"]
    assert -70.0 <= lufs <= 0.0, f"LUFS {lufs} outside [-70, 0]"


def test_loudness_normalize_to_minus14(
    client: httpx.Client, staged_audio: str,
) -> None:
    """target_lufs=-14 produces a staged WAV whose remeasured LUFS is within
    0.5 dB of the target."""
    target = -14
    out = f"out/loudnorm-{secrets.token_hex(8)}.wav"
    r = client.post(
        "/v1/audio/normalize",
        json={
            "file_path": staged_audio,
            "target_lufs": target,
            "output_format": "wav",
            "output_path": out,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("path") == out

    fetched = client.get(f"/v1/files/{out}")
    assert fetched.status_code == 200
    assert_wav(fetched.content)

    # Round-trip: re-measure the staged output.
    rt = client.post("/v1/audio/loudness", json={"file_path": out})
    assert rt.status_code == 200, rt.text
    post_lufs = rt.json()["loudness_lufs"]
    assert abs(post_lufs - target) <= 0.5, (
        f"output LUFS {post_lufs} not within 0.5 of target {target}"
    )


def test_loudness_bad_input_400(client: httpx.Client) -> None:
    """Non-audio bytes → 400."""
    rel = f"uploads/junk-{secrets.token_hex(8)}.txt"
    put = client.put(
        f"/v1/files/{rel}",
        content=b"not audio",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert put.status_code in (200, 201)

    r = client.post("/v1/audio/loudness", json={"file_path": rel})
    assert r.status_code == 400, r.text
