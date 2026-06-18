"""End-to-end tests for ``POST /v1/audio/metadata``.

Mutagen-backed audio tag read/write. Without a tags arg → returns the
existing tag set + technical info. With tags (a JSON-encoded string) →
writes those tags and returns the updated set.
"""

from __future__ import annotations

import secrets

import httpx
import pytest

pytestmark = pytest.mark.engine("metadata")


@pytest.fixture
def staged_mp3(client: httpx.Client, staged_audio: str) -> str:
    """Convert the staged WAV fixture to MP3 via /v1/audio/convert and
    return the staged MP3 path. Replaces the bash test's docker-ffmpeg
    fixture builder."""
    out = f"uploads/audio-{secrets.token_hex(8)}.mp3"
    r = client.post(
        "/v1/audio/convert",
        json={
            "file_path": staged_audio,
            "output_format": "mp3",
            "output_path": out,
        },
    )
    assert r.status_code == 200, r.text
    return out


def test_metadata_read_wav_returns_info(
    client: httpx.Client, staged_audio: str,
) -> None:
    """WAV read returns numeric duration_sec + sample_rate=44100 + channels."""
    r = client.post("/v1/audio/metadata", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body["duration_sec"], (int, float))
    assert body["sample_rate"] == 44100
    assert isinstance(body["channels"], (int, float))


def test_metadata_read_mp3_returns_tags(
    client: httpx.Client, staged_mp3: str,
) -> None:
    """MP3 read returns title + artist (possibly empty) and tech info."""
    r = client.post("/v1/audio/metadata", json={"file_path": staged_mp3})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "title" in body
    assert "artist" in body
    assert "duration_sec" in body
    assert "sample_rate" in body


def test_metadata_write_tags_roundtrip_mp3(
    client: httpx.Client, staged_mp3: str,
) -> None:
    """Writing title + artist via tags (JSON string) round-trips through read."""
    r = client.post(
        "/v1/audio/metadata",
        json={
            "file_path": staged_mp3,
            "tags": '{"title":"My Track","artist":"Test Artist"}',
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("title") == "My Track"
    assert body.get("artist") == "Test Artist"


def test_metadata_bad_tags_json_400(
    client: httpx.Client, staged_mp3: str,
) -> None:
    """Tags string that isn't valid JSON → 400/422, with 'tags' in detail."""
    r = client.post(
        "/v1/audio/metadata",
        json={"file_path": staged_mp3, "tags": "not-json-at-all"},
    )
    assert r.status_code in (400, 422), r.text
    assert "tags" in r.text.lower()


def test_metadata_nonexistent_file(client: httpx.Client) -> None:
    """Nonexistent staged file → 400/404/422."""
    r = client.post(
        "/v1/audio/metadata",
        json={"file_path": "nonexistent/path/file.wav"},
    )
    assert r.status_code in (400, 404, 422), r.text


def test_metadata_write_without_output_marks_persisted_false(
    client: httpx.Client, staged_mp3: str,
) -> None:
    """Write mode without an output target — tags applied in memory and
    response carries persisted=false so callers know the source file
    on disk wasn't touched. Regression for v1.0.10."""
    r = client.post(
        "/v1/audio/metadata",
        json={
            "file_path": staged_mp3,
            "tags": '{"title":"InMem","artist":"NoPersist"}',
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("title") == "InMem"
    assert body.get("artist") == "NoPersist"
    assert body.get("persisted") is False


def test_metadata_write_with_output_path_persists(
    client: httpx.Client, staged_mp3: str,
) -> None:
    """Write mode WITH output_path persists the tagged audio there.
    Read-back of the persisted file MUST show the new tags. This is
    the v1.0.10 fix — pre-fix the write was in-memory only."""
    dest = f"uploads/tagged-{secrets.token_hex(8)}.mp3"
    r = client.post(
        "/v1/audio/metadata",
        json={
            "file_path": staged_mp3,
            "tags": '{"title":"Persisted","artist":"OnDisk"}',
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body.get("path") == dest
    assert body.get("persisted") is True
    assert body.get("tags", {}).get("title") == "Persisted"
    assert body.get("tags", {}).get("artist") == "OnDisk"

    # Read the persisted file's tags back — they MUST match.
    rb = client.post("/v1/audio/metadata", json={"file_path": dest})
    assert rb.status_code == 200, rb.text
    rb_body = rb.json()
    assert rb_body.get("title") == "Persisted"
    assert rb_body.get("artist") == "OnDisk"
