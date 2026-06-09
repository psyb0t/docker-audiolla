"""End-to-end tests for the four MIR endpoints: beats, onsets, melody, segments.

All ride on the librosa-analyze engine. Beats has additional click-track
modes (base64 / output_path); melody supports as_midi → base64 MIDI.
"""

from __future__ import annotations

import base64

import httpx
import pytest

from .helpers import assert_midi, assert_wav

pytestmark = pytest.mark.engine("librosa-analyze")


# ── /v1/audio/beats ──────────────────────────────────────────────────────────


def test_beats_returns_tempo_and_beats(
    client: httpx.Client, staged_audio: str,
) -> None:
    """tempo_bpm is a number, beats is an array, duration is roughly 8s."""
    r = client.post("/v1/audio/beats", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["tempo_bpm"], (int, float))
    assert isinstance(body["beats"], list)
    assert 7.0 < body["duration"] < 9.0


def test_beats_click_track_base64_is_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """click_track=true returns base64-encoded WAV in click_track_base64."""
    r = client.post(
        "/v1/audio/beats",
        json={"file_path": staged_audio, "click_track": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    b64 = body.get("click_track_base64")
    assert b64, f"missing click_track_base64: {body}"
    decoded = base64.b64decode(b64)
    assert_wav(decoded, min_bytes=100)


def test_beats_click_track_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """click_track=true + output_path stages the WAV; beats array stays in JSON."""
    r = client.post(
        "/v1/audio/beats",
        json={
            "file_path": staged_audio,
            "click_track": True,
            "output_path": "mir/click.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "mir/click.wav"
    assert isinstance(body["beats"], list)

    fetched = client.get("/v1/files/mir/click.wav")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_beats_start_bpm(client: httpx.Client, staged_audio: str) -> None:
    """start_bpm hint accepted, response shape unchanged."""
    r = client.post(
        "/v1/audio/beats",
        json={"file_path": staged_audio, "start_bpm": 140},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["tempo_bpm"], (int, float))
    assert isinstance(body["beats"], list)


def test_beats_click_fixture_bpm_in_range(
    client: httpx.Client, staged_beat: str,
) -> None:
    """120-BPM click track → tempo_bpm in [100, 150]."""
    r = client.post("/v1/audio/beats", json={"file_path": staged_beat})
    assert r.status_code == 200, r.text
    body = r.json()
    bpm = body["tempo_bpm"]
    assert 100 < bpm < 150, f"BPM {bpm} not in [100,150]"


# ── /v1/audio/onsets ─────────────────────────────────────────────────────────


def test_onsets_returns_list(client: httpx.Client, staged_audio: str) -> None:
    """onsets is an array, count is a number, each onset has time + strength."""
    r = client.post("/v1/audio/onsets", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["onsets"], list)
    assert isinstance(body["count"], (int, float))
    for o in body["onsets"]:
        assert "time" in o
        assert "strength" in o


# ── /v1/audio/melody ─────────────────────────────────────────────────────────


def test_melody_contour(client: httpx.Client, staged_audio: str) -> None:
    """440 Hz sine fixture → at least one voiced contour frame near 440 Hz."""
    r = client.post("/v1/audio/melody", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["contour"], list)
    voiced_440 = [
        c for c in body["contour"]
        if c.get("voiced") is True
        and c.get("hz") is not None
        and 400 < float(c["hz"]) < 500
    ]
    assert len(voiced_440) >= 1, (
        f"no voiced ~440Hz frames; first few: {body['contour'][:5]}"
    )


def test_melody_as_midi(client: httpx.Client, staged_audio: str) -> None:
    """as_midi=true returns base64-encoded MIDI in midi_base64."""
    r = client.post(
        "/v1/audio/melody",
        json={"file_path": staged_audio, "as_midi": True},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    b64 = body.get("midi_base64")
    assert b64, f"missing midi_base64: {str(body)[:500]}"
    decoded = base64.b64decode(b64)
    assert_midi(decoded, min_bytes=14)


# ── /v1/audio/segments ───────────────────────────────────────────────────────


def test_segments_returns_ranges(client: httpx.Client, staged_audio: str) -> None:
    """num_segments=3 → segments array with start_sec, end_sec, label per entry."""
    r = client.post(
        "/v1/audio/segments",
        json={"file_path": staged_audio, "num_segments": 3},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["segments"], list)
    assert len(body["segments"]) > 0
    first = body["segments"][0]
    for key in ("start_sec", "end_sec", "label"):
        assert key in first, f"missing {key} in segment: {first}"
