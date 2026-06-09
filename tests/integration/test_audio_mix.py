"""End-to-end test for ``POST /v1/audio/mix``.

Multi-track mix. Requires at least 2 inputs (file_paths or file_urls).
"""

from __future__ import annotations

import httpx

from .helpers import assert_mp3, assert_wav


def _stage_two_tracks(client: httpx.Client, staged: str) -> tuple[str, str]:
    """Derive two trimmed staged tracks from the staged_audio fixture."""
    for name, end in (("mix/track_a.wav", 4.0), ("mix/track_b.wav", 4.0)):
        r = client.post(
            "/v1/audio/trim",
            json={
                "file_path": staged,
                "start_sec": 0.0,
                "end_sec": end,
                "output_path": name,
            },
        )
        assert r.status_code == 200, r.text
    return "mix/track_a.wav", "mix/track_b.wav"


def test_mix_returns_wav(client: httpx.Client, staged_audio: str) -> None:
    """Two tracks → 200; the staged output is a valid WAV."""
    a, b = _stage_two_tracks(client, staged_audio)
    r = client.post(
        "/v1/audio/mix",
        json={
            "file_paths": [a, b],
            "output_path": "out/mix.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_mix_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    a, b = _stage_two_tracks(client, staged_audio)
    r = client.post(
        "/v1/audio/mix",
        json={
            "file_paths": [a, b],
            "output_format": "mp3",
            "output_path": "out/mix.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_mix_one_track_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Mix requires ≥2 inputs — single-track → 400."""
    a, _ = _stage_two_tracks(client, staged_audio)
    r = client.post(
        "/v1/audio/mix",
        json={
            "file_paths": [a],
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_mix_invalid_tracks_type_422(client: httpx.Client) -> None:
    """file_paths must be a list — passing a string → Pydantic 422."""
    r = client.post(
        "/v1/audio/mix",
        json={"file_paths": "not-a-list"},
    )
    assert r.status_code == 422, r.text


def test_mix_missing_inputs_400(client: httpx.Client) -> None:
    """Neither file_paths nor file_urls → handler-level 400 (XOR)."""
    r = client.post("/v1/audio/mix", json={})
    assert r.status_code == 400, r.text


def test_mix_missing_track_file_404(
    client: httpx.Client, staged_audio: str,
) -> None:
    """A non-existent path in the array → 404 (propagated from resolver)."""
    a, _ = _stage_two_tracks(client, staged_audio)
    r = client.post(
        "/v1/audio/mix",
        json={
            "file_paths": [a, "mix/ghost-missing.wav"],
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_mix_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    a, b = _stage_two_tracks(client, staged_audio)
    r = client.post(
        "/v1/audio/mix",
        json={
            "file_paths": [a, b],
            "output_path": "mix/mixed.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "mix/mixed.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)
