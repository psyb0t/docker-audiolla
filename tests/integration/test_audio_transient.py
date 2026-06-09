"""End-to-end test for ``POST /v1/audio/transient``.

Transient shaper via dual-compressor attack/sustain blending.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav

pytestmark = pytest.mark.engine("fx-chain")


def test_transient_default_params_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Default attack/sustain gain → valid WAV at staged path."""
    r = client.post(
        "/v1/audio/transient",
        json={
            "file_path": staged_audio,
            "output_path": "out/transient.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100_000)


def test_transient_attack_boost(
    client: httpx.Client, staged_audio: str,
) -> None:
    """attack_gain_db=6 with sustain unchanged → 200."""
    r = client.post(
        "/v1/audio/transient",
        json={
            "file_path": staged_audio,
            "attack_gain_db": 6,
            "sustain_gain_db": 0,
            "output_path": "out/transient_attack.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_transient_sustain_cut(
    client: httpx.Client, staged_audio: str,
) -> None:
    """attack_gain_db=3 with sustain_gain_db=-6 → 200."""
    r = client.post(
        "/v1/audio/transient",
        json={
            "file_path": staged_audio,
            "attack_gain_db": 3,
            "sustain_gain_db": -6,
            "output_path": "out/transient_sustain.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_transient_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries `path` + echoed attack_gain_db; staged file fetchable."""
    r = client.post(
        "/v1/audio/transient",
        json={
            "file_path": staged_audio,
            "attack_gain_db": 3,
            "output_path": "transient_test/shaped.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "transient_test/shaped.wav"
    assert body["attack_gain_db"] == 3

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)
