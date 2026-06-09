"""End-to-end test for ``POST /v1/midi/drum``.

Step-sequencer MIDI synthesis. JSON body has a pattern with kick / snare /
hihat / etc. arrays of 0/1, plus tempo + bars.
"""

from __future__ import annotations

import secrets

import httpx
import pytest

from .helpers import assert_midi

pytestmark = pytest.mark.engine("midi-compose")


def test_drum_basic_pattern(client: httpx.Client) -> None:
    """4-on-the-floor kick + backbeat snare + 16ths hihat → valid MIDI."""
    dest = f"drum/basic-{secrets.token_hex(4)}.mid"
    r = client.post(
        "/v1/midi/drum",
        params={"output_path": dest},
        json={
            "tempo_bpm": 120,
            "steps": 16,
            "bars": 2,
            "pattern": {
                "kick":  [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0],
                "snare": [0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
                "hihat": [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1],
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == dest
    assert body["size"] >= 50

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_midi(fetched.content, min_bytes=50)


def test_drum_output_path(client: httpx.Client) -> None:
    """output_path stages MIDI under the requested path."""
    dest = f"drum_test/beat-{secrets.token_hex(4)}.mid"
    r = client.post(
        "/v1/midi/drum",
        params={"output_path": dest},
        json={
            "tempo_bpm": 90,
            "steps": 8,
            "pattern": {
                "kick": [1, 0, 1, 0, 1, 0, 1, 0],
                "snare": [0, 0, 1, 0, 0, 0, 1, 0],
            },
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == dest

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_midi(fetched.content)


def test_drum_swing(client: httpx.Client) -> None:
    """swing parameter is accepted."""
    dest = f"drum/swing-{secrets.token_hex(4)}.mid"
    r = client.post(
        "/v1/midi/drum",
        params={"output_path": dest},
        json={
            "tempo_bpm": 95,
            "swing": 0.3,
            "steps": 8,
            "pattern": {
                "kick": [1, 0, 0, 0, 1, 0, 0, 0],
                "hihat": [1, 1, 1, 1, 1, 1, 1, 1],
            },
        },
    )
    assert r.status_code == 200, r.text


def test_drum_missing_pattern_400(client: httpx.Client) -> None:
    """Body missing the required `pattern` field → 400 or 422."""
    r = client.post(
        "/v1/midi/drum",
        params={"output_path": f"drum/bad-{secrets.token_hex(4)}.mid"},
        json={"tempo_bpm": 120, "steps": 16},
    )
    assert r.status_code in (400, 422), r.text
