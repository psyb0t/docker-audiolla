"""End-to-end test for ``POST /v1/midi/humanize``.

Adds timing + velocity jitter to MIDI notes. Deterministic given a seed.
"""

from __future__ import annotations

import secrets

import httpx
import pytest

from .helpers import assert_midi

pytestmark = pytest.mark.engine("midi-compose")


_COMPOSE_SPEC = {
    "tempo_bpm": 120,
    "time_signature": [4, 4],
    "tracks": [
        {
            "name": "Lead",
            "program": 0,
            "channel": 0,
            "notes": [
                {"pitch": 60, "start_beats": 0.0, "duration_beats": 0.5, "velocity": 100},
                {"pitch": 64, "start_beats": 0.5, "duration_beats": 0.5, "velocity": 100},
                {"pitch": 67, "start_beats": 1.0, "duration_beats": 0.5, "velocity": 100},
            ],
        },
    ],
}


def _stage_midi(client: httpx.Client) -> str:
    dest = f"midi/hum-in-{secrets.token_hex(4)}.mid"
    r = client.post("/v1/midi/compose", params={"output_path": dest}, json=_COMPOSE_SPEC)
    assert r.status_code == 200, r.text
    return dest


def test_humanize_returns_midi(client: httpx.Client) -> None:
    """Default params produce a valid MThd file."""
    src = _stage_midi(client)
    dest = f"midi/hum-out-{secrets.token_hex(4)}.mid"
    r = client.post(
        "/v1/midi/humanize",
        json={"file_path": src, "output_path": dest},
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_midi(fetched.content, min_bytes=20)


def test_humanize_seed_deterministic(client: httpx.Client) -> None:
    """Same seed → byte-identical output."""
    src = _stage_midi(client)
    dest1 = f"midi/hum-{secrets.token_hex(4)}-a.mid"
    dest2 = f"midi/hum-{secrets.token_hex(4)}-b.mid"
    r1 = client.post(
        "/v1/midi/humanize",
        json={"file_path": src, "seed": 42, "output_path": dest1},
    )
    r2 = client.post(
        "/v1/midi/humanize",
        json={"file_path": src, "seed": 42, "output_path": dest2},
    )
    assert r1.status_code == 200, r1.text
    assert r2.status_code == 200, r2.text

    b1 = client.get(f"/v1/files/{dest1}").content
    b2 = client.get(f"/v1/files/{dest2}").content
    assert b1 == b2


def test_humanize_output_path_response_fields(client: httpx.Client) -> None:
    """Response surfaces both the staged path and the timing_ms parameter."""
    src = _stage_midi(client)
    dest = f"midi/hum-out-{secrets.token_hex(4)}.mid"
    r = client.post(
        "/v1/midi/humanize",
        json={
            "file_path": src,
            "timing_ms": 5,
            "velocity_pct": 5,
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == dest
    assert body["timing_ms"] == 5

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_midi(fetched.content)


def test_humanize_non_midi_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """A WAV file in file_path → 400."""
    r = client.post(
        "/v1/midi/humanize",
        json={
            "file_path": staged_audio,
            "output_path": f"midi/hum-{secrets.token_hex(4)}.mid",
        },
    )
    assert r.status_code == 400, r.text


def test_humanize_invalid_timing_400(client: httpx.Client) -> None:
    """timing_ms=1000 is out of range → 400."""
    src = _stage_midi(client)
    r = client.post(
        "/v1/midi/humanize",
        json={
            "file_path": src,
            "timing_ms": 1000,
            "output_path": f"midi/hum-{secrets.token_hex(4)}.mid",
        },
    )
    assert r.status_code == 400, r.text
