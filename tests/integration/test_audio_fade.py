"""End-to-end test for ``POST /v1/audio/fade``.

Apply fade-in and/or fade-out via ffmpeg afade. At least one of
fade_in/fade_out must be > 0.
"""

from __future__ import annotations

import httpx

from .helpers import assert_mp3, assert_wav


def test_fade_in_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """fade_in only returns a valid WAV at the staged path."""
    r = client.post(
        "/v1/audio/fade",
        json={
            "file_path": staged_audio,
            "fade_in": 1.0,
            "output_path": "out/fade_in.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_fade_out_only(client: httpx.Client, staged_audio: str) -> None:
    """fade_out only → 200."""
    r = client.post(
        "/v1/audio/fade",
        json={
            "file_path": staged_audio,
            "fade_out": 2.0,
            "output_path": "out/fade_out.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_fade_both(client: httpx.Client, staged_audio: str) -> None:
    """Both fade_in and fade_out specified → 200."""
    r = client.post(
        "/v1/audio/fade",
        json={
            "file_path": staged_audio,
            "fade_in": 1.0,
            "fade_out": 1.0,
            "output_path": "out/fade_both.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_fade_custom_curve(
    client: httpx.Client, staged_audio: str,
) -> None:
    """curve=qsin is a valid ffmpeg afade curve → 200."""
    r = client.post(
        "/v1/audio/fade",
        json={
            "file_path": staged_audio,
            "fade_in": 1.0,
            "curve": "qsin",
            "output_path": "out/fade_qsin.wav",
        },
    )
    assert r.status_code == 200, r.text


def test_fade_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    r = client.post(
        "/v1/audio/fade",
        json={
            "file_path": staged_audio,
            "fade_in": 1.0,
            "output_format": "mp3",
            "output_path": "out/fade.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_fade_neither_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Neither fade_in nor fade_out > 0 → 400 (or 422)."""
    r = client.post(
        "/v1/audio/fade",
        json={
            "file_path": staged_audio,
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_fade_missing_file_404(client: httpx.Client) -> None:
    """file_path pointing to a non-staged file → 404."""
    r = client.post(
        "/v1/audio/fade",
        json={
            "file_path": "no/such.wav",
            "fade_in": 1.0,
            "output_path": "out/missing.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_fade_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    r = client.post(
        "/v1/audio/fade",
        json={
            "file_path": staged_audio,
            "fade_in": 1.0,
            "fade_out": 1.0,
            "output_path": "fade/out.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "fade/out.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_fade_accepts_sec_suffix_aliases(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Both `fade_in_sec` and `fade_out_sec` work as aliases of the
    canonical `fade_in` / `fade_out` fields. Consistent with the rest
    of the API (`start_sec`, `end_sec`, `duration_sec`, etc.)."""
    r = client.post(
        "/v1/audio/fade",
        json={
            "file_path": staged_audio,
            "fade_in_sec": 1.0,
            "fade_out_sec": 1.0,
            "output_format": "mp3",
            "output_path": "out/fade_sec.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_fade_sec_alias_wins_over_legacy(
    client: httpx.Client, staged_audio: str,
) -> None:
    """If both `fade_in` and `fade_in_sec` are supplied, the _sec alias
    wins (per the schema docstring)."""
    r = client.post(
        "/v1/audio/fade",
        json={
            "file_path": staged_audio,
            "fade_in": 0.0,
            "fade_in_sec": 0.5,
            "output_path": "out/fade_alias.wav",
        },
    )
    assert r.status_code == 200, r.text
