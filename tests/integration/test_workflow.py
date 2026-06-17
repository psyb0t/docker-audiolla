"""End-to-end tests for the workflow / discoverability endpoints.

Covers ``GET /v1/catalog``, ``GET /v1/ops``, ``GET /v1/presets``,
``GET /v1/presets/{name}``, ``POST /v1/pipeline``.

Pipeline + presets currently take multipart form bodies (steps as a JSON
string in a form field). Engine markers cover the ops used in the
pipeline tests; the discoverability endpoints don't need any engine.
"""

from __future__ import annotations

import json
import secrets

import httpx
import pytest

from .helpers import assert_wav

pytestmark = pytest.mark.engine("librosa-analyze", "fx-chain")


# ── discoverability (no engines needed) ─────────────────────────────────────


def test_catalog_returns_categories(client: httpx.Client) -> None:
    """/v1/catalog enumerates endpoint categories with > 5 entries."""
    r = client.get("/v1/catalog")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "catalog"
    assert isinstance(body["categories"], list)
    assert len(body["categories"]) > 5
    names = {cat["name"] for cat in body["categories"]}
    assert "workflow" in names
    dynamics = next(c for c in body["categories"] if c["name"] == "dynamics")
    assert len(dynamics["endpoints"]) > 0


def test_ops_returns_list(client: httpx.Client) -> None:
    """/v1/ops lists every pipeline op slug."""
    r = client.get("/v1/ops")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["object"] == "list"
    ops = body["data"]
    assert isinstance(ops, list) and len(ops) > 10
    for needed in ("trim", "eq", "normalize", "multiband_compress", "fx"):
        assert needed in ops, f"missing op {needed!r}; got {ops}"


def test_presets_list(client: httpx.Client) -> None:
    """/v1/presets lists at least 3 curated workflows."""
    r = client.get("/v1/presets")
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["data"]) >= 3
    names = {p["name"] for p in body["data"]}
    for needed in ("podcast-cleanup", "master-for-spotify", "vocal-cleanup"):
        assert needed in names, f"missing preset {needed!r}; got {names}"


def test_presets_describe(client: httpx.Client) -> None:
    """/v1/presets/{name} returns the full step list."""
    r = client.get("/v1/presets/master-for-spotify")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["name"] == "master-for-spotify"
    assert len(body["steps"]) >= 2
    assert body["steps"][0]["op"] == "multiband_compress"


def test_presets_describe_unknown_404(client: httpx.Client) -> None:
    """Unknown preset → 404."""
    r = client.get("/v1/presets/does-not-exist")
    assert r.status_code == 404, r.text


def test_engines_includes_load_status(client: httpx.Client) -> None:
    """/v1/engines includes the per-engine `loaded` + `idle_seconds`."""
    r = client.get("/v1/engines")
    assert r.status_code == 200, r.text
    body = r.json()
    first = body["data"][0]
    assert "loaded" in first
    assert "idle_seconds" in first


# ── pipeline (multipart form) ──────────────────────────────────────────────


def test_pipeline_run_2step(client: httpx.Client, staged_audio: str) -> None:
    """Ad-hoc pipeline (trim → reverse) produces a usable WAV smaller than input."""
    dest = f"pipe/out-{secrets.token_hex(4)}.wav"
    r = client.post(
        "/v1/pipeline",
        json={
            "file_path": staged_audio,
            "steps": [
                {"op": "trim", "params": {"start_sec": 0, "end_sec": 2}},
                {"op": "reverse", "params": {}},
            ],
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    # 2s of 44.1k stereo ≈ 350 KB; require at least 100 KB.
    assert_wav(fetched.content, min_bytes=100_000)


def test_pipeline_output_path_step_log(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Response includes the executed step log + path."""
    dest = f"pipe/log-{secrets.token_hex(4)}.wav"
    r = client.post(
        "/v1/pipeline",
        json={
            "file_path": staged_audio,
            "steps": [{"op": "reverse", "params": {}}],
            "output_path": dest,
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["path"] == dest
    assert len(body["steps"]) == 1
    assert body["steps"][0]["op"] == "reverse"


def test_pipeline_unknown_op_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Unknown op slug → 400/422."""
    r = client.post(
        "/v1/pipeline",
        json={
            "file_path": staged_audio,
            "steps": [{"op": "this_op_does_not_exist", "params": {}}],
            "output_path": f"pipe/bad-{secrets.token_hex(4)}.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_pipeline_bad_steps_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Malformed `steps` (string instead of array) → 422."""
    r = client.post(
        "/v1/pipeline",
        json={
            "file_path": staged_audio,
            "steps": "{not valid json",
            "output_path": f"pipe/bad-{secrets.token_hex(4)}.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_pipeline_empty_steps_400(
    client: httpx.Client, staged_audio: str,
) -> None:
    """Empty `steps` array → 400/422."""
    r = client.post(
        "/v1/pipeline",
        data={
            "file_path": staged_audio,
            "steps": "[]",
            "output_path": f"pipe/empty-{secrets.token_hex(4)}.wav",
        },
    )
    assert r.status_code in (400, 422), r.text


def test_preset_run_accepts_json_body(
    client: httpx.Client, staged_audio: str,
) -> None:
    """`POST /v1/presets/{name}` now takes a JSON body (was Form/File
    in older versions). Pick the first registered preset to exercise."""
    presets = client.get("/v1/presets").json()
    names = [p.get("name") for p in presets.get("data", presets.get("presets", []))]
    if not names:
        import pytest as _pt
        _pt.skip("no presets registered on this image")
    name = names[0]
    r = client.post(
        f"/v1/presets/{name}",
        json={
            "file_path": staged_audio,
            "output_format": "mp3",
            "output_path": "out/preset_run.mp3",
        },
        timeout=180.0,
    )
    assert r.status_code == 200, r.text


def test_pipeline_accepts_json_body(
    client: httpx.Client, staged_audio: str,
) -> None:
    """`POST /v1/pipeline` now takes a JSON body. Typed `steps` array."""
    r = client.post(
        "/v1/pipeline",
        json={
            "file_path": staged_audio,
            "steps": [
                {"op": "normalize", "params": {"target_lufs": -14}},
                {"op": "trim", "params": {"start_sec": 0, "end_sec": 4}},
            ],
            "output_format": "wav",
            "output_path": "out/pipe_json.wav",
        },
        timeout=180.0,
    )
    assert r.status_code == 200, r.text
