"""End-to-end test for ``POST /v1/audio/concat``.

Concatenate N audio files in order. Requires at least 2 inputs.
"""

from __future__ import annotations

import httpx

from .helpers import assert_mp3, assert_wav


def _stage_two_parts(client: httpx.Client, staged: str) -> tuple[str, str]:
    """Trim the staged fixture into two non-overlapping segments."""
    for name, (start, end) in (
        ("concat/part_a.wav", (0.0, 3.0)),
        ("concat/part_b.wav", (3.0, 6.0)),
    ):
        r = client.post(
            "/v1/audio/trim",
            json={
                "file_path": staged,
                "start_sec": start,
                "end_sec": end,
                "output_path": name,
            },
        )
        assert r.status_code == 200, r.text
    return "concat/part_a.wav", "concat/part_b.wav"


def test_concat_returns_wav(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Two parts → 200; staged output is a valid WAV."""
    a, b = _stage_two_parts(client, staged_audio)
    r = client.post(
        "/v1/audio/concat",
        json={
            "file_paths": [a, b],
            "output_path": "out/concat.wav",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)


def test_concat_output_longer_than_part(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Concatenated output's duration > a single part's duration."""
    a, b = _stage_two_parts(client, staged_audio)
    r = client.post(
        "/v1/audio/concat",
        json={
            "file_paths": [a, b],
            "output_path": "concat/joined.wav",
        },
    )
    assert r.status_code == 200, r.text

    part_info = client.post("/v1/audio/info", json={"file_path": a})
    joined_info = client.post(
        "/v1/audio/info", json={"file_path": "concat/joined.wav"},
    )
    part_dur = float(part_info.json()["duration_sec"])
    joined_dur = float(joined_info.json()["duration_sec"])
    assert joined_dur > part_dur


def test_concat_output_format_mp3(
    client: httpx.Client, staged_audio: str,
) -> None:
    """output_format=mp3 produces a valid MP3."""
    a, b = _stage_two_parts(client, staged_audio)
    r = client.post(
        "/v1/audio/concat",
        json={
            "file_paths": [a, b],
            "output_format": "mp3",
            "output_path": "out/concat.mp3",
        },
    )
    assert r.status_code == 200, r.text
    fetched = client.get(f"/v1/files/{r.json()['path']}")
    assert fetched.status_code == 200
    assert_mp3(fetched.content)


def test_concat_one_file_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """concat requires ≥2 inputs → 400."""
    a, _ = _stage_two_parts(client, staged_audio)
    r = client.post(
        "/v1/audio/concat",
        json={
            "file_paths": [a],
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_concat_invalid_files_type_422(client: httpx.Client) -> None:
    """file_paths must be a list — string → Pydantic 422."""
    r = client.post(
        "/v1/audio/concat",
        json={"file_paths": "not-a-list"},
    )
    assert r.status_code == 422, r.text


def test_concat_missing_inputs_400(client: httpx.Client) -> None:
    """Neither file_paths nor file_urls → handler-level 400 (XOR)."""
    r = client.post("/v1/audio/concat", json={})
    assert r.status_code == 400, r.text


def test_concat_missing_file_in_array_404(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Missing file in the array → 404 (propagated from resolver)."""
    a, _ = _stage_two_parts(client, staged_audio)
    r = client.post(
        "/v1/audio/concat",
        json={
            "file_paths": [a, "concat/ghost-missing.wav"],
            "output_path": "out/bad.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_concat_output_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries `path`; staged file is fetchable WAV."""
    a, b = _stage_two_parts(client, staged_audio)
    r = client.post(
        "/v1/audio/concat",
        json={
            "file_paths": [a, b],
            "output_path": "concat/joined2.wav",
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == "concat/joined2.wav"
    fetched = client.get(f"/v1/files/{body['path']}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=100)
