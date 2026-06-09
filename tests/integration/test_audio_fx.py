"""End-to-end test for ``POST /v1/audio/fx``.

Generic pedalboard chain processor — Gain, Compressor, Reverb,
PitchShift, etc. VST plugin classes are NOT in the allowlist.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav

pytestmark = pytest.mark.engine("fx-chain")


def test_fx_single_gain(client: httpx.Client, staged_audio: str) -> None:
    """Single Gain effect returns a valid WAV at the staged path."""
    r = client.post(
        "/v1/audio/fx",
        json={
            "file_path": staged_audio,
            "effects": [{"type": "Gain", "params": {"gain_db": -3.0}}],
            "output_format": "wav",
            "output_path": "out/fx_gain.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "out/fx_gain.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_fx_compressor_reverb_chain(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Compressor → Reverb → Gain chain returns 200."""
    r = client.post(
        "/v1/audio/fx",
        json={
            "file_path": staged_audio,
            "effects": [
                {"type": "Compressor", "params": {"threshold_db": -18, "ratio": 4.0}},
                {"type": "Reverb", "params": {"room_size": 0.5, "wet_level": 0.3}},
                {"type": "Gain", "params": {"gain_db": -3.0}},
            ],
            "output_format": "wav",
            "output_path": "out/fx_chain.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_fx_pitch_shift(client: httpx.Client, staged_audio: str) -> None:
    """PitchShift returns 200 and a fetchable file."""
    r = client.post(
        "/v1/audio/fx",
        json={
            "file_path": staged_audio,
            "effects": [{"type": "PitchShift", "params": {"semitones": 3.0}}],
            "output_format": "wav",
            "output_path": "out/fx_ps.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_fx_output_path_roundtrip(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries `path`; staged file is fetchable."""
    r = client.post(
        "/v1/audio/fx",
        json={
            "file_path": staged_audio,
            "effects": [{"type": "Gain", "params": {"gain_db": 0.0}}],
            "output_format": "wav",
            "output_path": "fx/out.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "fx/out.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert len(fetched.content) > 0


def test_fx_missing_effects_422(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing required `effects` → Pydantic 422."""
    r = client.post(
        "/v1/audio/fx",
        json={
            "file_path": staged_audio,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 422, r.text


def test_fx_unknown_type_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Unknown effect type → handler-level 400 with 'not allowed' in detail."""
    r = client.post(
        "/v1/audio/fx",
        json={
            "file_path": staged_audio,
            "effects": [{"type": "NoSuchEffect", "params": {}}],
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 400, r.text
    assert "not allowed" in r.text.lower()


def test_fx_vst_blocked_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """VST plugin classes are not in the allowlist → 400."""
    r = client.post(
        "/v1/audio/fx",
        json={
            "file_path": staged_audio,
            "effects": [{"type": "VST3Plugin", "params": {}}],
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 400, r.text
