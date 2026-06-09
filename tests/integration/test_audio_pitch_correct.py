"""End-to-end test for ``POST /v1/audio/pitch-correct``.

Auto-tune style pitch correction that snaps detected pitches to the
nearest semitone with a configurable strength. Uses librosa-analyze for
the detection step. CPU-only.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav

pytestmark = pytest.mark.engine("librosa-analyze")


def test_pitch_correct_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Default strength: staged file is a decodable WAV."""
    r = client.post(
        "/v1/audio/pitch-correct",
        json={
            "file_path": staged_audio,
            "output_path": "out/pc.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/pc.wav"
    assert body["size"] > 100

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_pitch_correct_bypass(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``strength=0`` is a near-bypass; output size should be within ~10 %
    of the input. (Encoder differences mean we can't assert byte-identity,
    just rough size parity.)"""
    r = client.post(
        "/v1/audio/pitch-correct",
        json={
            "file_path": staged_audio,
            "strength": 0,
            "output_path": "out/pc_bypass.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()

    # fetch the source to compare sizes
    src = client.get(f"/v1/files/{staged_audio}")
    assert src.status_code == 200
    in_sz = len(src.content)
    out_sz = body["size"]
    assert abs(out_sz - in_sz) <= in_sz // 10, (
        f"bypass output too different (in={in_sz}, out={out_sz})"
    )


def test_pitch_correct_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``output_path`` is echoed and the staged file is fetchable."""
    r = client.post(
        "/v1/audio/pitch-correct",
        json={
            "file_path": staged_audio,
            "output_path": "pc_test/corrected.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "pc_test/corrected.wav"

    fetched = client.get("/v1/files/pc_test/corrected.wav")
    assert fetched.status_code == 200
    assert_wav(fetched.content)


def test_pitch_correct_invalid_strength(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``strength`` outside [0, 1] is rejected."""
    r = client.post(
        "/v1/audio/pitch-correct",
        json={
            "file_path": staged_audio,
            "strength": 2.0,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text
