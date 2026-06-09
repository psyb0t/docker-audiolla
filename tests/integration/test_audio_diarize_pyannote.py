"""End-to-end test for ``POST /v1/audio/diarize/pyannote``.

pyannote.audio speaker diarization (``pyannote/speaker-diarization-3.1``).
Weights are HuggingFace-licence-gated — operator must accept the
``pyannote/segmentation-3.0`` + ``pyannote/speaker-diarization-3.1``
licences with an HF token in the env. CPU-capable but slow. Marked
``hf_gated``.

Diarize is a JSON-only endpoint — it returns ``{segments, num_speakers}``
and writes no audio.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = [
    pytest.mark.engine("pyannote"),
    pytest.mark.hf_gated,
]


def test_diarize_returns_segments(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Happy path: response carries a ``segments`` array and a
    non-negative ``num_speakers`` integer.

    Synthetic sine input has zero human speech, so pyannote correctly
    returns ``num_speakers == 0`` and an empty ``segments`` list.
    Real-audio inputs return ≥ 1. The test validates the contract
    (shape + types + non-negative count), not the model's choice."""
    r = client.post(
        "/v1/audio/diarize/pyannote",
        json={"file_path": staged_audio},
        timeout=600.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("segments"), list)
    assert isinstance(body.get("num_speakers"), int)
    assert body["num_speakers"] >= 0


def test_diarize_with_num_speakers_hint(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Passing ``num_speakers=2`` as a hint still produces a segments
    array (pyannote pins the cluster count to 2 in this case)."""
    r = client.post(
        "/v1/audio/diarize/pyannote",
        json={"file_path": staged_audio, "num_speakers": 2},
        timeout=600.0,
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert isinstance(body.get("segments"), list)


def test_diarize_rejects_unknown_engine(
    client: httpx.Client, staged_audio: str,
) -> None:
    """An engine slug that's not registered → 404."""
    r = client.post(
        "/v1/audio/diarize/nonexistent",
        json={"file_path": staged_audio},
    )
    assert r.status_code == 404, r.text


def test_diarize_requires_input(client: httpx.Client) -> None:
    """Missing both file_path and file_url → 400 (xor validator)."""
    r = client.post("/v1/audio/diarize/pyannote", json={})
    assert r.status_code == 400, r.text
