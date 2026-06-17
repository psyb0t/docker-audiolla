"""End-to-end test for ``POST /v1/audio/remix``.

Stem-separate then bounce back with per-stem gain/mute control. The happy
path requires a separation engine (htdemucs, GPU-only); these tests cover
the error paths that fire before any model inference and so work on a CPU
container with only ``librosa-analyze`` loaded.
"""

from __future__ import annotations

import httpx
import pytest

pytestmark = pytest.mark.engine("librosa-analyze")


def test_remix_unknown_engine_404(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Unknown engine slug → 404 from the ENGINES.get() guard."""
    r = client.post(
        "/v1/audio/remix",
        json={
            "file_path": staged_audio,
            "engine": "no-such-engine",
            "output_path": "out/r.wav",
        },
    )
    assert r.status_code == 404, r.text


def test_remix_non_separation_engine_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """A loaded engine that doesn't implement ``separate()`` → 400."""
    r = client.post(
        "/v1/audio/remix",
        json={
            "file_path": staged_audio,
            "engine": "librosa-analyze",
            "output_path": "out/r.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_remix_invalid_stem_mix_json(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``stem_mix`` as malformed JSON string → 422 from Pydantic
    (rejects non-object before the handler sees it)."""
    r = client.post(
        "/v1/audio/remix",
        json={
            "file_path": staged_audio,
            "engine": "librosa-analyze",
            "stem_mix": "not-json{{{",
            "output_path": "out/r.wav",
        },
    )
    assert r.status_code == 422, r.text


def test_remix_stem_mix_array_rejected(
    client: httpx.Client, staged_audio: str,
) -> None:
    """``stem_mix`` as an array (not an object) → 422 from Pydantic."""
    r = client.post(
        "/v1/audio/remix",
        json={
            "file_path": staged_audio,
            "engine": "librosa-analyze",
            "stem_mix": [1, 2, 3],
            "output_path": "out/r.wav",
        },
    )
    assert r.status_code == 422, r.text


def test_remix_non_separation_engine_short_circuits_missing_file(
    client: httpx.Client,
) -> None:
    """Engine check (400) fires BEFORE the file resolver runs, so even a
    bogus ``file_path`` produces 400, not 404."""
    r = client.post(
        "/v1/audio/remix",
        json={
            "file_path": "nosuch/audio.wav",
            "engine": "librosa-analyze",
            "output_path": "out/r.wav",
        },
    )
    assert r.status_code == 400, r.text


def test_remix_linear_gain_shorthand_no_500(
    client: httpx.Client, staged_audio: str,
) -> None:
    """`stem_mix={"vocals": 1.0, "drums": 0.0}` (linear-gain shorthand)
    used to 500 with a plain-text body because the handler did
    `spec.get("mute")` on a float. Now: 0.0 mutes, 1.0 passes unity,
    intermediate maps via 20*log10. CPU image doesn't have htdemucs
    weights cached, so we just check the 500 → JSON contract by
    asserting the response is JSON (success OR a JSON error)."""
    r = client.post(
        "/v1/audio/remix",
        json={
            "file_path": staged_audio,
            "engine": "htdemucs",
            "stem_mix": {"vocals": 1.0, "drums": 0.0, "bass": 0.0, "other": 0.0},
            "output_format": "mp3",
            "output_path": "out/remix_linear.mp3",
        },
        timeout=600.0,
    )
    # Either succeeds OR returns a JSON-shaped error — both are fine for
    # this regression. The bug was a plain-text "Internal Server Error".
    assert r.headers.get("content-type", "").startswith("application/json"), (
        f"non-JSON response body: {r.text[:300]}"
    )


def test_remix_unsupported_stem_mix_value_type_rejected(
    client: httpx.Client, staged_audio: str,
) -> None:
    """`stem_mix={"vocals": "loud"}` (string) is rejected — Pydantic
    catches it at the schema layer (additionalProperties: number) with
    422, before the handler. Either 400 or 422 is acceptable; the
    important thing is the response is JSON-shaped, not a plain-text
    500 (which is the regression we're guarding against)."""
    r = client.post(
        "/v1/audio/remix",
        json={
            "file_path": staged_audio,
            "engine": "htdemucs",
            "stem_mix": {"vocals": "loud"},
            "output_format": "mp3",
            "output_path": "out/remix_bad.mp3",
        },
        timeout=120.0,
    )
    assert r.status_code in (400, 422), r.text
    assert r.headers.get("content-type", "").startswith("application/json")
