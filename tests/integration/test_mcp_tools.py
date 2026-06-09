"""End-to-end tests for MCP tool invocation via JSON-RPC tools/call.

Each tool wraps a REST endpoint; covers happy paths for compose / render
/ generate / fx / analyze / transform / loudness, plus the error path
(bad args come back as ``isError=true``, NOT HTTP 500) and put_file /
get_file / list_files / delete_file round-trips.
"""

from __future__ import annotations

import base64
import hashlib
import os
import secrets

import httpx
import pytest

from .helpers import assert_midi, assert_wav

pytestmark = pytest.mark.engine(
    "midi-compose", "midi-render", "fx-chain", "librosa-analyze", "sox-transform",
)


_MCP_HEADERS = {
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}


SPEC = {
    "tempo_bpm": 120,
    "tracks": [
        {
            "name": "Lead", "program": 0, "channel": 0,
            "notes": [
                {"pitch": 60, "start_beats": 0.0, "duration_beats": 0.5, "velocity": 100},
                {"pitch": 64, "start_beats": 0.5, "duration_beats": 0.5, "velocity": 100},
                {"pitch": 67, "start_beats": 1.0, "duration_beats": 0.5, "velocity": 100},
                {"pitch": 72, "start_beats": 1.5, "duration_beats": 0.5, "velocity": 100},
            ],
        },
        {
            "name": "Kick", "program": 0, "channel": 9,
            "notes": [
                {"pitch": 36, "start_beats": 0.0, "duration_beats": 0.1, "velocity": 110},
                {"pitch": 36, "start_beats": 1.0, "duration_beats": 0.1, "velocity": 110},
            ],
        },
    ],
}


def _mcp_call(client: httpx.Client, payload: dict) -> dict:
    """Send a JSON-RPC POST, return the parsed body."""
    r = client.post("/v1/mcp/", headers=_MCP_HEADERS, json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def _structured(body: dict) -> dict:
    """Pull the structuredContent dict off a tools/call response."""
    assert body["result"].get("isError") is not True, body
    return body["result"]["structuredContent"]


# ── handshake-free tools/list ─────────────────────────────────────────────


def test_mcp_tools_list_has_new_tools(client: httpx.Client) -> None:
    """tools/list lists every expected MCP tool name."""
    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {},
    })
    names = {tool["name"] for tool in body["result"]["tools"]}
    expected = {
        "fx", "midi_compose", "midi_render", "midi_generate",
        "separate", "master", "analyze", "transform", "loudness",
        "list_engines", "list_files", "put_file", "get_file", "delete_file",
    }
    missing = expected - names
    assert not missing, f"tools/list missing: {missing}"


def test_mcp_list_engines(client: httpx.Client) -> None:
    """list_engines reflects the engines actually configured for this session."""
    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "list_engines", "arguments": {}},
    })
    engines = _structured(body)["engines"]
    slugs = {e["slug"] for e in engines}
    for required in (
        "midi-compose", "midi-render", "fx-chain",
        "librosa-analyze", "sox-transform",
    ):
        assert required in slugs, f"missing engine {required}; got {slugs}"


# ── midi_compose / midi_generate / midi_render ────────────────────────────


def test_mcp_midi_compose_writes_smf(client: httpx.Client) -> None:
    """midi_compose tool with output_path stages a real MThd file."""
    dest = f"mcp/compose-{secrets.token_hex(4)}.mid"
    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 10, "method": "tools/call",
        "params": {
            "name": "midi_compose",
            "arguments": {"spec": SPEC, "output_path": dest},
        },
    })
    result = _structured(body)
    assert result["path"] == dest
    size = result["size"]
    assert size > 0

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_midi(fetched.content)
    assert len(fetched.content) == size


def test_mcp_midi_generate_writes_wav(client: httpx.Client) -> None:
    """midi_generate one-shots compose + render → staged WAV."""
    dest = f"mcp/generate-{secrets.token_hex(4)}.wav"
    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 11, "method": "tools/call",
        "params": {
            "name": "midi_generate",
            "arguments": {
                "spec": SPEC, "output_format": "wav", "output_path": dest,
            },
        },
    })
    result = _structured(body)
    assert result["path"] == dest

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=1000)


def test_mcp_midi_render_with_file_path(client: httpx.Client) -> None:
    """midi_compose to stage, then midi_render with file_path → staged WAV."""
    mid = f"mcp/render-in-{secrets.token_hex(4)}.mid"
    _mcp_call(client, {
        "jsonrpc": "2.0", "id": 20, "method": "tools/call",
        "params": {
            "name": "midi_compose",
            "arguments": {"spec": SPEC, "output_path": mid},
        },
    })

    wav = f"mcp/render-out-{secrets.token_hex(4)}.wav"
    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 21, "method": "tools/call",
        "params": {
            "name": "midi_render",
            "arguments": {
                "file_path": mid, "output_format": "wav", "output_path": wav,
            },
        },
    })
    result = _structured(body)
    assert result["path"] == wav

    fetched = client.get(f"/v1/files/{wav}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=1000)


# ── fx via a staged file ──────────────────────────────────────────────────


def test_mcp_fx_chain_with_staged_file(
    client: httpx.Client, staged_audio: str,
) -> None:
    """fx tool applies a 3-effect chain → staged WAV."""
    dest = f"mcp/fx-{secrets.token_hex(4)}.wav"
    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 31, "method": "tools/call",
        "params": {
            "name": "fx",
            "arguments": {
                "file_path": staged_audio,
                "effects": [
                    {"type": "Compressor", "params": {"threshold_db": -18, "ratio": 4.0}},
                    {"type": "Reverb", "params": {"room_size": 0.5, "wet_level": 0.3}},
                    {"type": "Gain", "params": {"gain_db": -3.0}},
                ],
                "output_format": "wav",
                "output_path": dest,
            },
        },
    })
    result = _structured(body)
    assert result["path"] == dest

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=1000)


# ── error path: bad args → isError=true, not HTTP 500 ────────────────────


def test_mcp_tool_error_returns_iserror_not_500(client: httpx.Client) -> None:
    """midi_compose with out-of-range pitch → isError=true with mention of pitch."""
    r = client.post(
        "/v1/mcp/",
        headers=_MCP_HEADERS,
        json={
            "jsonrpc": "2.0", "id": 40, "method": "tools/call",
            "params": {
                "name": "midi_compose",
                "arguments": {
                    "spec": {
                        "tempo_bpm": 120,
                        "tracks": [{
                            "program": 0, "channel": 0,
                            "notes": [
                                {"pitch": 999, "start_beats": 0,
                                 "duration_beats": 1, "velocity": 100},
                            ],
                        }],
                    },
                },
            },
        },
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["result"]["isError"] is True, body
    assert "pitch" in r.text.lower()


# ── put_file / get_file round-trip ──────────────────────────────────────


def test_mcp_put_get_roundtrip(client: httpx.Client) -> None:
    """put_file + get_file via MCP preserves bytes; verified by sha256."""
    payload = os.urandom(128)
    content_b64 = base64.b64encode(payload).decode("ascii")
    path = f"mcp/roundtrip-{secrets.token_hex(4)}.bin"

    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 50, "method": "tools/call",
        "params": {
            "name": "put_file",
            "arguments": {"path": path, "content_base64": content_b64},
        },
    })
    assert _structured(body)["path"] == path

    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 51, "method": "tools/call",
        "params": {"name": "get_file", "arguments": {"path": path}},
    })
    result = _structured(body)
    assert result["path"] == path
    assert result["size"] == len(payload)

    # Verify the bytes via REST.
    fetched = client.get(f"/v1/files/{path}")
    assert fetched.status_code == 200
    assert hashlib.sha256(fetched.content).hexdigest() == (
        hashlib.sha256(payload).hexdigest()
    )


# ── analyze / transform / loudness / normalize via MCP ────────────────────


def test_mcp_analyze_via_file_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """analyze tool returns bpm + duration; fixture is a steady 8s tone."""
    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 110, "method": "tools/call",
        "params": {
            "name": "analyze",
            "arguments": {
                "file_path": staged_audio,
                "features": ["bpm", "duration", "loudness"],
            },
        },
    })
    result = _structured(body)
    assert 7 < result["duration"] < 9
    assert result.get("bpm") is not None


def test_mcp_transform_via_file_path(
    client: httpx.Client, staged_audio: str,
) -> None:
    """transform tool applies gain + reverb → staged WAV."""
    dest = f"mcp/transform-{secrets.token_hex(4)}.wav"
    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 120, "method": "tools/call",
        "params": {
            "name": "transform",
            "arguments": {
                "file_path": staged_audio,
                "operations": [
                    {"op": "gain", "params": {"db": -3}},
                    {"op": "reverb", "params": {"reverberance": 50}},
                ],
                "output_format": "wav",
                "output_path": dest,
            },
        },
    })
    result = _structured(body)
    assert result["path"] == dest

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=1000)


def test_mcp_loudness_measure(
    client: httpx.Client, staged_audio: str,
) -> None:
    """loudness tool returns loudness_lufs (measure-only, no normalization)."""
    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 130, "method": "tools/call",
        "params": {"name": "loudness", "arguments": {"file_path": staged_audio}},
    })
    result = _structured(body)
    assert result.get("loudness_lufs") is not None


def test_mcp_normalize(
    client: httpx.Client, staged_audio: str,
) -> None:
    """normalize tool with target_lufs writes audio + reports measured_lufs."""
    dest = f"mcp/normalize-{secrets.token_hex(4)}.wav"
    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 131, "method": "tools/call",
        "params": {
            "name": "normalize",
            "arguments": {
                "file_path": staged_audio,
                "target_lufs": -14,
                "output_format": "wav",
                "output_path": dest,
            },
        },
    })
    result = _structured(body)
    assert result["path"] == dest
    assert result.get("measured_lufs") is not None

    fetched = client.get(f"/v1/files/{dest}")
    assert fetched.status_code == 200
    assert_wav(fetched.content, min_bytes=1000)


# ── list_files / delete_file ─────────────────────────────────────────────


def test_mcp_list_files(client: httpx.Client) -> None:
    """list_files returns a files array; after staging via REST it appears."""
    marker = f"mcp/list-{secrets.token_hex(4)}.bin"
    client.put(
        f"/v1/files/{marker}", content=b"marker",
        headers={"Content-Type": "application/octet-stream"},
    )

    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 140, "method": "tools/call",
        "params": {"name": "list_files", "arguments": {}},
    })
    files = _structured(body)["files"]
    assert isinstance(files, list)
    paths = [f["path"] for f in files]
    assert marker in paths


def test_mcp_delete_file(client: httpx.Client) -> None:
    """delete_file removes the file (verified via REST GET → 404)."""
    target = f"mcp/to-delete-{secrets.token_hex(4)}.txt"
    put = client.put(
        f"/v1/files/{target}", content=b"marker",
        headers={"Content-Type": "application/octet-stream"},
    )
    assert put.status_code == 201

    body = _mcp_call(client, {
        "jsonrpc": "2.0", "id": 150, "method": "tools/call",
        "params": {"name": "delete_file", "arguments": {"path": target}},
    })
    assert body["result"].get("isError") is not True

    follow = client.get(f"/v1/files/{target}")
    assert follow.status_code == 404
