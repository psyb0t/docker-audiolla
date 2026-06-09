"""End-to-end test for ``POST /v1/audio/master``.

Mastering dispatches to one of two engines based on ``mode``:

- ``mode="reference"`` → matchering (reference-based LUFS / spectral match)
- ``mode="chain"``     → pedalboard-chain (preset-driven static chain)

CPU-fine. Not engine-dispatched in the URL — engine selection is implicit
in ``mode``. Marked with both engine slugs so the harness brings both up.
"""

from __future__ import annotations

import httpx
import pytest

from .helpers import assert_wav

pytestmark = [
    pytest.mark.engine("matchering", "pedalboard-chain"),
]


# ── chain mode (pedalboard-chain) ───────────────────────────────────────────


def test_master_chain_transparent(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``mode=chain preset=transparent`` → 200 + decodable WAV."""
    r = client.post(
        "/v1/audio/master",
        json={
            "file_path": staged_audio,
            "mode": "chain",
            "preset": "transparent",
            "output_format": "wav",
            "output_path": "out/master_chain_transparent.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "pedalboard-chain"
    assert body["mode"] == "chain"
    assert body["output_format"] == "wav"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_master_chain_loud(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``mode=chain preset=loud`` → 200 + decodable WAV."""
    r = client.post(
        "/v1/audio/master",
        json={
            "file_path": staged_audio,
            "mode": "chain",
            "preset": "loud",
            "output_path": "out/master_chain_loud.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "pedalboard-chain"
    assert body["mode"] == "chain"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_master_chain_rejects_unknown_preset(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``mode=chain`` with a preset that's not in the registry → 400."""
    r = client.post(
        "/v1/audio/master",
        json={
            "file_path": staged_audio,
            "mode": "chain",
            "preset": "not-a-preset",
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_master_chain_requires_preset(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``mode=chain`` without a preset → 400 (preset is required for chain)."""
    r = client.post(
        "/v1/audio/master",
        json={
            "file_path": staged_audio,
            "mode": "chain",
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 400, r.text


# ── reference mode (matchering) ─────────────────────────────────────────────


def test_master_reference_real(
    client: httpx.Client, staged_audio: str, staged_reference: str,
) -> None:
    """``mode=reference`` with a real reference file → 200 + decodable WAV.

    ``staged_audio`` (the synthetic 440 Hz fixture) is the target;
    ``staged_reference`` (a -6 dB version of the same fixture) is the
    reference. matchering refuses byte-identical inputs, so the -6 dB
    derivation matters."""
    r = client.post(
        "/v1/audio/master",
        json={
            "file_path": staged_audio,
            "mode": "reference",
            "reference_path": staged_reference,
            "output_path": "out/master_reference.wav",
        },
        timeout=300.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["engine"] == "matchering"
    assert body["mode"] == "reference"

    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=10_000)


def test_master_reference_missing_reference(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``mode=reference`` without ``reference_path``/``reference_url`` → 400."""
    r = client.post(
        "/v1/audio/master",
        json={
            "file_path": staged_audio,
            "mode": "reference",
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 400, r.text


# ── shared validators ──────────────────────────────────────────────────────


def test_master_rejects_unknown_mode(
    client: httpx.Client, staged_audio: str,
) -> None:
    """A ``mode`` value outside {reference, chain} → 400 or 422."""
    r = client.post(
        "/v1/audio/master",
        json={
            "file_path": staged_audio,
            "mode": "bogus",
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_master_requires_input(client: httpx.Client) -> None:
    """Missing both file_path and file_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/master",
        json={
            "mode": "chain",
            "preset": "transparent",
            "output_path": "out/x.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_master_requires_output(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing both output_path and output_url → 400 (xor validator)."""
    r = client.post(
        "/v1/audio/master",
        json={
            "file_path": staged_audio,
            "mode": "chain",
            "preset": "transparent",
        },
    )
    assert r.status_code == 400, r.text
