"""End-to-end tests for ``POST /v1/audio/dj-prep``.

Combined DJ-prep: BPM + key + Camelot wheel position + integrated LUFS.
JSON-only response. Needs librosa-analyze + chord-detect engines.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.engine("librosa-analyze", "chord-detect")


def test_dj_prep_response_shape(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response carries bpm, key, camelot, integrated_lufs."""
    r = client.post("/v1/audio/dj-prep", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    body = r.json()
    for field in ("bpm", "key", "camelot", "integrated_lufs"):
        assert field in body, f"missing field {field!r}: {body}"


def test_dj_prep_click_track_bpm(
    client: httpx.Client, staged_beat: str,
) -> None:
    """120-BPM click track → bpm in [100, 150]."""
    r = client.post("/v1/audio/dj-prep", json={"file_path": staged_beat})
    assert r.status_code == 200, r.text
    bpm = r.json()["bpm"]
    assert bpm is not None
    assert 100 < bpm < 150, f"bpm {bpm} not in [100,150]"


def test_dj_prep_lufs_is_number_or_null(
    client: httpx.Client, staged_audio: str,
) -> None:
    """integrated_lufs is either a number or null."""
    r = client.post("/v1/audio/dj-prep", json={"file_path": staged_audio})
    assert r.status_code == 200, r.text
    lufs = r.json()["integrated_lufs"]
    assert lufs is None or isinstance(lufs, (int, float))
