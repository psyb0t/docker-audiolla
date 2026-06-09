"""End-to-end tests for ``POST /v1/midi/inspect`` and ``POST /v1/midi/transform``.

inspect reads back a MIDI file's structure (tempo, tracks, note counts).
transform mutates a MIDI in place — transpose, channel-filter, tempo
override, optional inline quantize.
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
        {
            "name": "Kick",
            "program": 0,
            "channel": 9,
            "notes": [
                {"pitch": 36, "start_beats": 0.0, "duration_beats": 0.1, "velocity": 110},
                {"pitch": 36, "start_beats": 1.0, "duration_beats": 0.1, "velocity": 110},
            ],
        },
    ],
}


def _stage_demo_midi(client: httpx.Client) -> str:
    dest = f"midi/utils-in-{secrets.token_hex(4)}.mid"
    r = client.post(
        "/v1/midi/compose",
        params={"output_path": dest},
        json=_COMPOSE_SPEC,
    )
    assert r.status_code == 200, r.text
    return dest


# ── inspect ────────────────────────────────────────────────────────────────


def test_inspect_returns_structure(client: httpx.Client) -> None:
    """inspect surfaces tempo + track names of a composed MIDI."""
    src = _stage_demo_midi(client)
    r = client.post("/v1/midi/inspect", json={"file_path": src})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["type"] == 1
    tempos = body["tempo_changes"]
    assert tempos and 119 < tempos[0]["bpm"] < 121
    names = [t["name"] for t in body["tracks"]]
    assert "Lead" in names
    assert "Kick" in names


def test_inspect_rejects_non_midi(client: httpx.Client) -> None:
    """Non-MIDI bytes → 400 with detail mentioning MThd."""
    bogus = f"uploads/not-midi-{secrets.token_hex(4)}.bin"
    put = client.put(
        f"/v1/files/{bogus}",
        content=b"definitely not a midi file",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert put.status_code in (200, 201)

    r = client.post("/v1/midi/inspect", json={"file_path": bogus})
    assert r.status_code == 400, r.text
    assert "mthd" in r.text.lower()


# ── transform ──────────────────────────────────────────────────────────────


def test_transform_transpose_preserves_note_count(client: httpx.Client) -> None:
    """+12 semitone transpose keeps the lead track's note count unchanged."""
    src = _stage_demo_midi(client)
    dest = f"midi/utils-tx-{secrets.token_hex(4)}.mid"

    r = client.post(
        "/v1/midi/transform",
        json={
            "file_path": src,
            "transpose_semitones": 12,
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text

    before = client.post("/v1/midi/inspect", json={"file_path": src}).json()
    after = client.post("/v1/midi/inspect", json={"file_path": dest}).json()
    lead_before = next(t for t in before["tracks"] if t["name"] == "Lead")
    lead_after = next(t for t in after["tracks"] if t["name"] == "Lead")
    assert lead_before["note_on_count"] == lead_after["note_on_count"]


def test_transform_drop_drums(client: httpx.Client) -> None:
    """drop_channels="9" removes the kick track (channel 9)."""
    src = _stage_demo_midi(client)
    dest = f"midi/utils-tx-{secrets.token_hex(4)}.mid"

    r = client.post(
        "/v1/midi/transform",
        json={
            "file_path": src,
            "drop_channels": "9",
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text

    after = client.post("/v1/midi/inspect", json={"file_path": dest}).json()
    for track in after["tracks"]:
        assert 9 not in track.get("channels", [])


def test_transform_keep_channels(client: httpx.Client) -> None:
    """keep_channels="0" whitelists only the lead, dropping channel 9."""
    src = _stage_demo_midi(client)
    dest = f"midi/utils-tx-{secrets.token_hex(4)}.mid"

    r = client.post(
        "/v1/midi/transform",
        json={
            "file_path": src,
            "keep_channels": "0",
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text

    after = client.post("/v1/midi/inspect", json={"file_path": dest}).json()
    for track in after["tracks"]:
        assert 9 not in track.get("channels", [])


def test_transform_tempo_override(client: httpx.Client) -> None:
    """tempo_bpm=200 flips the tempo of the rewritten file."""
    src = _stage_demo_midi(client)
    dest = f"midi/utils-tx-{secrets.token_hex(4)}.mid"

    r = client.post(
        "/v1/midi/transform",
        json={
            "file_path": src,
            "tempo_bpm": 200,
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["path"] == dest

    after = client.post("/v1/midi/inspect", json={"file_path": dest}).json()
    assert 199 < after["tempo_changes"][0]["bpm"] < 201


def test_transform_quantize_grid_beats(client: httpx.Client) -> None:
    """Inline quantize_grid_beats=0.25 still produces a MIDI file."""
    src = _stage_demo_midi(client)
    dest = f"midi/utils-tx-{secrets.token_hex(4)}.mid"

    r = client.post(
        "/v1/midi/transform",
        json={
            "file_path": src,
            "quantize_grid_beats": 0.25,
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{dest}")
    assert_midi(fetched.content)


def test_transform_both_keep_drop_400(client: httpx.Client) -> None:
    """keep_channels + drop_channels together → 400 (mutually exclusive)."""
    src = _stage_demo_midi(client)
    r = client.post(
        "/v1/midi/transform",
        json={
            "file_path": src,
            "keep_channels": "0",
            "drop_channels": "9",
            "output_path": f"midi/utils-tx-{secrets.token_hex(4)}.mid",
        },
    )
    assert r.status_code == 400, r.text
