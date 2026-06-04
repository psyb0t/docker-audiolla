"""HTTP-level tests for new audiolla server endpoints:

  POST /v1/audio/restore/{engine}
  POST /v1/audio/to_midi
  POST /v1/audio/enhance
  POST /v1/audio/visualize/image/spectrogram
  POST /v1/audio/visualize/image/waveform
  POST /v1/audio/visualize/video/{mode}
  POST /v1/audio/fingerprint
  POST /v1/audio/silence

All tests patch audiolla.server.ENGINES and audiolla.server.MCP_SERVER so
no real engines, model weights, or external subprocesses are needed.
"""

from __future__ import annotations

import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import audiolla.server as _server_mod


# ── shared test infrastructure ────────────────────────────────────────────────


@asynccontextmanager
async def _noop_session():
    yield


def _noop_mcp() -> MagicMock:
    m = MagicMock()
    m.session_manager.run = _noop_session
    return m


def _make_ffmpeg_engine() -> MagicMock:
    eng = MagicMock()
    eng.loaded.return_value = False
    eng.last_used_secs_ago.return_value = None
    eng.spectrogram = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    eng.waveform = AsyncMock(return_value=b"\x89PNG\r\n\x1a\n" + b"\x00" * 50)
    eng.visualize = AsyncMock(return_value=b"\x00\x00\x00\x1cftyp" + b"\x00" * 50)
    return eng


def _make_fingerprint_engine() -> MagicMock:
    eng = MagicMock()
    eng.loaded.return_value = False
    eng.last_used_secs_ago.return_value = None
    eng.compute = AsyncMock(return_value={"duration": 8.0, "fingerprint": "ABCDE12345"})
    return eng


def _make_silence_engine() -> MagicMock:
    eng = MagicMock()
    eng.loaded.return_value = False
    eng.last_used_secs_ago.return_value = None
    eng.detect = AsyncMock(return_value={
        "silent_ranges": [],
        "non_silent_ranges": [{"start_sec": 0.0, "end_sec": 8.0}],
        "duration": 8.0,
        "threshold_db": -30.0,
        "min_duration_sec": 0.5,
    })
    return eng


def _make_uvr_restore_engine() -> MagicMock:
    eng = MagicMock()
    eng.loaded.return_value = False
    eng.last_used_secs_ago.return_value = None
    eng.restore = AsyncMock(return_value=b"RIFF" + b"\x00" * 100)
    return eng


def _make_basic_pitch_engine() -> MagicMock:
    eng = MagicMock()
    eng.loaded.return_value = False
    eng.last_used_secs_ago.return_value = None
    eng.to_midi = AsyncMock(return_value=b"MThd" + b"\x00" * 20)
    return eng


def _make_deepfilter_engine() -> MagicMock:
    eng = MagicMock()
    eng.loaded.return_value = False
    eng.last_used_secs_ago.return_value = None
    eng.enhance = AsyncMock(return_value=b"RIFF" + b"\x00" * 100)
    eng._df_state = MagicMock()
    return eng


# Each test builds its own TestClient to keep ENGINES patches clean.

def _client_for(engines: dict, registry: dict | None = None, tmp_files_dir: Path | None = None) -> TestClient:
    if tmp_files_dir is None:
        tmp_files_dir = Path(tempfile.mkdtemp()) / "files"
        tmp_files_dir.mkdir(parents=True, exist_ok=True)
    if registry is None:
        registry = {slug: {"executor": "mock"} for slug in engines}
    with patch("audiolla.server.config.FILES_DIR", tmp_files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", engines, clear=True), \
         patch.dict("audiolla.server.REGISTRY", registry, clear=True):
        return TestClient(_server_mod.app)


# ── /v1/audio/visualize/image/spectrogram ────────────────────────────────────────


def test_spectrogram_200_returns_png():
    eng = _make_ffmpeg_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"ffmpeg-render": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"ffmpeg-render": {"executor": "ffmpeg_render"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/visualize/image/spectrogram",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    eng.spectrogram.assert_awaited_once()


def test_spectrogram_404_when_no_engine_configured():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/visualize/image/spectrogram",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


def test_spectrogram_404_when_engine_lacks_spectrogram_method():
    """When the engine registered as ffmpeg-render doesn't pass the duck-type
    check (missing spectrogram/waveform/visualize), the server returns 404."""
    bad_eng = MagicMock()
    bad_eng.loaded.return_value = False
    bad_eng.last_used_secs_ago.return_value = None
    # Has no spectrogram/waveform/visualize → is_ffmpeg_render_engine returns False
    del bad_eng.spectrogram

    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"ffmpeg-render": bad_eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"ffmpeg-render": {"executor": "ffmpeg_render"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/visualize/image/spectrogram",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


def test_spectrogram_output_path_returns_json():
    eng = _make_ffmpeg_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"ffmpeg-render": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"ffmpeg-render": {"executor": "ffmpeg_render"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/visualize/image/spectrogram",
                data={"output_path": "viz/spec.png"},
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "viz/spec.png"


# ── /v1/audio/visualize/image/waveform ───────────────────────────────────────────


def test_waveform_200_returns_png():
    eng = _make_ffmpeg_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"ffmpeg-render": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"ffmpeg-render": {"executor": "ffmpeg_render"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/visualize/image/waveform",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    assert "png" in r.headers["content-type"].lower()
    eng.waveform.assert_awaited_once()


def test_waveform_404_when_no_engine_configured():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/visualize/image/waveform",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


# ── /v1/audio/visualize/video/{mode} ────────────────────────────────────────────


def test_visualize_200_returns_video():
    eng = _make_ffmpeg_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"ffmpeg-render": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"ffmpeg-render": {"executor": "ffmpeg_render"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/visualize/video/spectrum",
                data={"container": "mp4"},
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    assert "video" in r.headers["content-type"].lower()
    eng.visualize.assert_awaited_once()


def test_visualize_400_for_unknown_mode():
    eng = _make_ffmpeg_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"ffmpeg-render": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"ffmpeg-render": {"executor": "ffmpeg_render"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/visualize/video/notamode",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 400
    assert "mode" in r.json()["detail"].lower()


def test_visualize_webm_container():
    eng = _make_ffmpeg_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"ffmpeg-render": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"ffmpeg-render": {"executor": "ffmpeg_render"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/visualize/video/waves",
                data={"container": "webm"},
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    assert "webm" in r.headers["content-type"].lower()


# ── /v1/audio/fingerprint ─────────────────────────────────────────────────────


def test_fingerprint_200_returns_json():
    eng = _make_fingerprint_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"audio-fingerprint": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"audio-fingerprint": {"executor": "audio_fingerprint"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/fingerprint",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    body = r.json()
    assert "fingerprint" in body
    assert "duration" in body
    eng.compute.assert_awaited_once()


def test_fingerprint_404_when_no_engine():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/fingerprint",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


def test_fingerprint_404_when_engine_lacks_compute():
    """When the engine registered as audio-fingerprint doesn't pass the duck-type
    check (missing compute), the server returns 404."""
    bad_eng = MagicMock()
    bad_eng.loaded.return_value = False
    bad_eng.last_used_secs_ago.return_value = None
    # Remove compute to fail duck-type check
    del bad_eng.compute

    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"audio-fingerprint": bad_eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"audio-fingerprint": {"executor": "audio_fingerprint"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/fingerprint",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


# ── /v1/audio/silence ─────────────────────────────────────────────────────────


def test_silence_200_returns_json():
    eng = _make_silence_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"silence-detect": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"silence-detect": {"executor": "silence_detect"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/silence",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    body = r.json()
    assert "silent_ranges" in body
    assert "non_silent_ranges" in body
    eng.detect.assert_awaited_once()


def test_silence_415_for_unsupported_output_format():
    eng = _make_silence_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"silence-detect": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"silence-detect": {"executor": "silence_detect"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/silence",
                data={"output_format": "xyz"},
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 415


def test_silence_404_when_no_engine():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/silence",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


def test_silence_output_path_when_trim_mode_set():
    """When trim_mode is set and output_path is given, the endpoint should
    route the trimmed audio to staging and return JSON with 'path'."""
    import base64
    trimmed_b64 = base64.b64encode(b"RIFF" + b"\x00" * 40).decode()

    eng = _make_silence_engine()
    eng.detect = AsyncMock(return_value={
        "silent_ranges": [{"start_sec": 1.0, "end_sec": 2.0, "duration_sec": 1.0}],
        "non_silent_ranges": [{"start_sec": 0.0, "end_sec": 1.0}, {"start_sec": 2.0, "end_sec": 5.0}],
        "duration": 5.0,
        "threshold_db": -30.0,
        "min_duration_sec": 0.5,
        "trim_mode": "edges",
        "output_format": "wav",
        "trimmed_audio_base64": trimmed_b64,
    })

    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"silence-detect": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"silence-detect": {"executor": "silence_detect"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/silence",
                data={"trim_mode": "edges", "output_path": "silence/trimmed.wav"},
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    body = r.json()
    assert body["path"] == "silence/trimmed.wav"


# ── /v1/audio/restore/{engine} — dereverb ───────────────────────────────────────


def test_dereverb_200_returns_audio():
    eng = _make_uvr_restore_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"uvr-dereverb": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"uvr-dereverb": {"executor": "uvr_separator", "model": "x.ckpt"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/restore/uvr-dereverb",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/")
    eng.restore.assert_awaited_once()


def test_dereverb_404_for_unknown_engine():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/restore/nonexistent",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404
    assert "nonexistent" in r.json()["detail"]


def test_dereverb_400_for_wrong_engine_type():
    """An engine that does not expose restore() (e.g. a fingerprint engine)
    should return 400 from dereverb."""
    wrong_eng = _make_fingerprint_engine()
    del wrong_eng.restore

    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"uvr-dereverb": wrong_eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"uvr-dereverb": {"executor": "uvr_separator", "model": "x.ckpt"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/restore/uvr-dereverb",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 400
    assert "restore" in r.json()["detail"].lower()


def test_dereverb_415_for_unsupported_output_format():
    eng = _make_uvr_restore_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"uvr-dereverb": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"uvr-dereverb": {"executor": "uvr_separator", "model": "x.ckpt"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/restore/uvr-dereverb",
                data={"output_format": "xyz"},
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 415


def test_dereverb_output_path_returns_json():
    eng = _make_uvr_restore_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"uvr-dereverb": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"uvr-dereverb": {"executor": "uvr_separator", "model": "x.ckpt"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/restore/uvr-dereverb",
                data={"output_path": "dereverb/out.wav"},
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    assert r.json()["path"] == "dereverb/out.wav"


# ── /v1/audio/restore/{engine} — deecho ─────────────────────────────────────────


def test_deecho_200_returns_audio():
    eng = _make_uvr_restore_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"uvr-deecho": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"uvr-deecho": {"executor": "uvr_separator", "model": "x.ckpt"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/restore/uvr-deecho",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    eng.restore.assert_awaited_once()


def test_deecho_404_for_unknown_engine():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/restore/nope",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


def test_deecho_400_for_wrong_engine_type():
    wrong_eng = _make_fingerprint_engine()
    del wrong_eng.restore

    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"uvr-deecho": wrong_eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"uvr-deecho": {"executor": "uvr_separator", "model": "x.ckpt"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/restore/uvr-deecho",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 400


# ── /v1/audio/restore/{engine} — denoise ────────────────────────────────────────


def test_denoise_200_returns_audio():
    eng = _make_uvr_restore_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"uvr-denoise": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"uvr-denoise": {"executor": "uvr_separator", "model": "x.ckpt"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/restore/uvr-denoise",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    eng.restore.assert_awaited_once()


def test_denoise_404_for_unknown_engine():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/restore/nope",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


# ── /v1/audio/to_midi ─────────────────────────────────────────────────────────


def test_to_midi_200_returns_midi():
    eng = _make_basic_pitch_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"basic-pitch": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"basic-pitch": {"executor": "basic_pitch"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/to_midi/basic-pitch",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    assert "midi" in r.headers["content-type"].lower()
    eng.to_midi.assert_awaited_once()


def test_to_midi_404_for_unknown_engine():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/to_midi/nonexistent",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


def test_to_midi_400_for_wrong_engine_type():
    wrong_eng = _make_fingerprint_engine()
    del wrong_eng.to_midi  # no to_midi → is_basic_pitch_engine returns False

    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"basic-pitch": wrong_eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"basic-pitch": {"executor": "basic_pitch"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/to_midi/basic-pitch",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 400
    assert "transcription" in r.json()["detail"].lower()


def test_to_midi_output_path_returns_json():
    eng = _make_basic_pitch_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"basic-pitch": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"basic-pitch": {"executor": "basic_pitch"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/to_midi/basic-pitch",
                data={"output_path": "midi/out.mid"},
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    assert r.json()["path"] == "midi/out.mid"


def test_to_midi_custom_thresholds_passed_to_engine():
    eng = _make_basic_pitch_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"basic-pitch": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"basic-pitch": {"executor": "basic_pitch"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/to_midi/basic-pitch",
                data={"onset_threshold": "0.8"},
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    call_kwargs = eng.to_midi.call_args.kwargs
    assert call_kwargs["onset_threshold"] == pytest.approx(0.8)


# ── /v1/audio/enhance ────────────────────────────────────────────────────────


def test_enhance_200_returns_audio():
    eng = _make_deepfilter_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"deepfilter": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"deepfilter": {"executor": "deepfilter"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/enhance/deepfilter",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("audio/")
    eng.enhance.assert_awaited_once()


def test_enhance_404_for_unknown_engine():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/enhance/nonexistent",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


def test_enhance_400_for_wrong_engine_type():
    """An engine without enhance() + _df_state should return 400."""
    wrong_eng = MagicMock()
    wrong_eng.loaded.return_value = False
    wrong_eng.last_used_secs_ago.return_value = None
    del wrong_eng.enhance
    del wrong_eng._df_state

    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"deepfilter": wrong_eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"deepfilter": {"executor": "deepfilter"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/enhance/deepfilter",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 400
    assert "enhancement" in r.json()["detail"].lower()


def test_enhance_415_for_unsupported_output_format():
    eng = _make_deepfilter_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"deepfilter": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"deepfilter": {"executor": "deepfilter"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/enhance/deepfilter",
                data={"output_format": "xyz"},
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 415


def test_enhance_output_path_returns_json():
    eng = _make_deepfilter_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"deepfilter": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"deepfilter": {"executor": "deepfilter"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/enhance/deepfilter",
                data={"output_path": "enhanced/out.wav"},
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    assert r.json()["path"] == "enhanced/out.wav"


# ── /v1/audio/chords ──────────────────────────────────────────────────────────


def _make_chord_detect_engine() -> MagicMock:
    eng = MagicMock()
    eng.loaded.return_value = False
    eng.last_used_secs_ago.return_value = None
    eng.detect_chords = AsyncMock(return_value={
        "key": "G major",
        "key_confidence": 0.85,
        "chords": [{"chord": "G major", "start_sec": 0.0, "end_sec": 2.0, "confidence": 0.9}],
        "duration": 8.0,
    })
    return eng


def test_chords_200_returns_json():
    eng = _make_chord_detect_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"chord-detect": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"chord-detect": {"executor": "chord_detect"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/chords",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    body = r.json()
    assert "key" in body
    assert "chords" in body
    eng.detect_chords.assert_awaited_once()


def test_chords_404_when_no_engine():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/chords",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


# ── /v1/audio/vad ─────────────────────────────────────────────────────────────


def _make_vad_engine() -> MagicMock:
    eng = MagicMock()
    eng.loaded.return_value = False
    eng.last_used_secs_ago.return_value = None
    eng.detect_voice = AsyncMock(return_value={
        "speech_segments": [{"start_sec": 0.5, "end_sec": 5.0, "duration_sec": 4.5}],
        "non_speech_segments": [],
        "speech_ratio": 0.75,
        "duration": 6.0,
        "threshold": 0.5,
    })
    return eng


def test_vad_200_returns_json():
    eng = _make_vad_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"silero-vad": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"silero-vad": {"executor": "vad"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/vad",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    body = r.json()
    assert "speech_segments" in body
    eng.detect_voice.assert_awaited_once()


def test_vad_404_when_no_engine():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/vad",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


# ── /v1/audio/diarize/{engine} ────────────────────────────────────────────────


def _make_diarize_engine() -> MagicMock:
    eng = MagicMock()
    eng.loaded.return_value = False
    eng.last_used_secs_ago.return_value = None
    eng.diarize = AsyncMock(return_value={
        "segments": [
            {"speaker": "SPEAKER_00", "start_sec": 0.0, "end_sec": 5.0, "duration_sec": 5.0},
            {"speaker": "SPEAKER_01", "start_sec": 5.0, "end_sec": 10.0, "duration_sec": 5.0},
        ],
        "num_speakers": 2,
        "speakers": ["SPEAKER_00", "SPEAKER_01"],
        "duration": 10.0,
    })
    return eng


def test_diarize_200_returns_json():
    eng = _make_diarize_engine()
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"pyannote": eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"pyannote": {"executor": "diarize_pyannote"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/diarize/pyannote",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 200
    body = r.json()
    assert "segments" in body
    assert "num_speakers" in body
    eng.diarize.assert_awaited_once()


def test_diarize_404_for_unknown_engine():
    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/diarize/nonexistent",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 404


def test_diarize_400_for_wrong_engine_type():
    wrong_eng = _make_fingerprint_engine()
    del wrong_eng.diarize

    files_dir = Path(tempfile.mkdtemp()) / "files"
    files_dir.mkdir()

    with patch("audiolla.server.config.FILES_DIR", files_dir), \
         patch("audiolla.server.MCP_SERVER", _noop_mcp()), \
         patch.dict("audiolla.server.ENGINES", {"pyannote": wrong_eng}, clear=True), \
         patch.dict("audiolla.server.REGISTRY", {"pyannote": {"executor": "diarize_pyannote"}}, clear=True):
        with TestClient(_server_mod.app) as c:
            r = c.post(
                "/v1/audio/diarize/pyannote",
                files={"file": ("a.wav", b"RIFF" + b"\x00" * 50, "audio/wav")},
            )

    assert r.status_code == 400
    assert "diarization" in r.json()["detail"].lower()
