"""Unit tests for AudioFingerprintEngine.

fpcalc is the prod-image chromaprint CLI.  All subprocess.run calls are
mocked so these tests run without fpcalc installed.
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from audiolla.engines.audio_fingerprint import AudioFingerprintEngine, FingerprintError


def _engine() -> AudioFingerprintEngine:
    return AudioFingerprintEngine(
        slug="audio-fingerprint", entry={"executor": "audio_fingerprint"}
    )


def _mock_proc(returncode: int = 0, stdout: str = "", stderr: str = "") -> MagicMock:
    p = MagicMock()
    p.returncode = returncode
    p.stdout = stdout
    p.stderr = stderr
    return p


# ── compute: happy path ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compute_returns_duration_and_fingerprint(tmp_path):
    payload = json.dumps({"duration": 215.34, "fingerprint": "AQADtEqRR"})
    mock_proc = _mock_proc(returncode=0, stdout=payload)

    eng = _engine()

    with patch("audiolla.engines.audio_fingerprint.to_wav_float32", return_value=str(tmp_path / "in.wav")), \
         patch("subprocess.run", return_value=mock_proc), \
         patch("os.unlink"):
        result = await eng.compute(b"audio", "audio.wav")

    assert result["duration"] == pytest.approx(215.34)
    assert result["fingerprint"] == "AQADtEqRR"
    assert "fingerprint_raw" not in result


@pytest.mark.asyncio
async def test_compute_includes_fingerprint_raw_when_requested(tmp_path):
    payload = json.dumps({"duration": 10.0, "fingerprint": "ABCDE"})
    json_proc = _mock_proc(returncode=0, stdout=payload)
    raw_proc = _mock_proc(returncode=0, stdout="FINGERPRINT=12,34,56,78")

    eng = _engine()

    with patch("audiolla.engines.audio_fingerprint.to_wav_float32", return_value=str(tmp_path / "in.wav")), \
         patch("subprocess.run", side_effect=[json_proc, raw_proc]), \
         patch("os.unlink"):
        result = await eng.compute(b"audio", "audio.wav", return_raw=True)

    assert result["fingerprint_raw"] == [12, 34, 56, 78]


@pytest.mark.asyncio
async def test_compute_handles_fpcalc_exit3(tmp_path):
    """fpcalc exit=3 (EOF during last frame) is treated as success when stdout is valid JSON."""
    payload = json.dumps({"duration": 8.0, "fingerprint": "XYZ"})
    mock_proc = _mock_proc(returncode=3, stdout=payload)

    eng = _engine()

    with patch("audiolla.engines.audio_fingerprint.to_wav_float32", return_value=str(tmp_path / "in.wav")), \
         patch("subprocess.run", return_value=mock_proc), \
         patch("os.unlink"):
        result = await eng.compute(b"audio", "audio.wav")

    assert result["fingerprint"] == "XYZ"


@pytest.mark.asyncio
async def test_compute_with_analyze_seconds_passes_length_flag(tmp_path):
    payload = json.dumps({"duration": 30.0, "fingerprint": "FP"})
    mock_proc = _mock_proc(returncode=0, stdout=payload)

    eng = _engine()
    captured_cmds = []

    def _capture_run(cmd, **_kwargs):
        captured_cmds.append(cmd)
        return mock_proc

    with patch("audiolla.engines.audio_fingerprint.to_wav_float32", return_value="/tmp/in.wav"), \
         patch("subprocess.run", side_effect=_capture_run), \
         patch("os.unlink"):
        await eng.compute(b"audio", "audio.wav", analyze_seconds=60.0)

    assert "-length" in captured_cmds[0]
    assert "60" in captured_cmds[0]


@pytest.mark.asyncio
async def test_compute_without_length_limit_omits_flag(tmp_path):
    payload = json.dumps({"duration": 30.0, "fingerprint": "FP"})
    mock_proc = _mock_proc(returncode=0, stdout=payload)

    eng = _engine()
    captured_cmds = []

    def _capture_run(cmd, **_kwargs):
        captured_cmds.append(cmd)
        return mock_proc

    with patch("audiolla.engines.audio_fingerprint.to_wav_float32", return_value="/tmp/in.wav"), \
         patch("subprocess.run", side_effect=_capture_run), \
         patch("os.unlink"):
        await eng.compute(b"audio", "audio.wav", analyze_seconds=0)

    assert "-length" not in captured_cmds[0]


# ── compute: error cases ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_compute_raises_when_analyze_seconds_negative():
    eng = _engine()
    with pytest.raises(FingerprintError, match="analyze_seconds must be >= 0"):
        await eng.compute(b"audio", "audio.wav", analyze_seconds=-1.0)


@pytest.mark.asyncio
async def test_compute_raises_when_fpcalc_not_found(tmp_path):
    eng = _engine()

    with patch("audiolla.engines.audio_fingerprint.to_wav_float32", return_value="/tmp/in.wav"), \
         patch("subprocess.run", side_effect=FileNotFoundError), \
         patch("os.unlink"):
        with pytest.raises(FingerprintError, match="fpcalc binary not found"):
            await eng.compute(b"audio", "audio.wav")


@pytest.mark.asyncio
async def test_compute_raises_on_nonzero_exit_with_empty_stdout(tmp_path):
    mock_proc = _mock_proc(returncode=1, stdout="", stderr="decode error")

    eng = _engine()

    with patch("audiolla.engines.audio_fingerprint.to_wav_float32", return_value="/tmp/in.wav"), \
         patch("subprocess.run", return_value=mock_proc), \
         patch("os.unlink"):
        with pytest.raises(FingerprintError, match="fpcalc exit=1"):
            await eng.compute(b"audio", "audio.wav")


@pytest.mark.asyncio
async def test_compute_raises_when_stdout_is_not_json(tmp_path):
    mock_proc = _mock_proc(returncode=0, stdout="not json at all")

    eng = _engine()

    with patch("audiolla.engines.audio_fingerprint.to_wav_float32", return_value="/tmp/in.wav"), \
         patch("subprocess.run", return_value=mock_proc), \
         patch("os.unlink"):
        with pytest.raises(FingerprintError, match="not JSON"):
            await eng.compute(b"audio", "audio.wav")


@pytest.mark.asyncio
async def test_compute_always_unlinks_wav_on_success(tmp_path):
    payload = json.dumps({"duration": 5.0, "fingerprint": "FP"})
    mock_proc = _mock_proc(returncode=0, stdout=payload)
    wav_path = "/tmp/fake.wav"
    unlinked = []

    eng = _engine()

    with patch("audiolla.engines.audio_fingerprint.to_wav_float32", return_value=wav_path), \
         patch("subprocess.run", return_value=mock_proc), \
         patch("os.unlink", side_effect=lambda p: unlinked.append(p)):
        await eng.compute(b"audio", "audio.wav")

    assert wav_path in unlinked


@pytest.mark.asyncio
async def test_compute_always_unlinks_wav_on_error(tmp_path):
    wav_path = "/tmp/fake.wav"
    unlinked = []

    eng = _engine()

    with patch("audiolla.engines.audio_fingerprint.to_wav_float32", return_value=wav_path), \
         patch("subprocess.run", side_effect=FileNotFoundError), \
         patch("os.unlink", side_effect=lambda p: unlinked.append(p)):
        with pytest.raises(FingerprintError):
            await eng.compute(b"audio", "audio.wav")

    assert wav_path in unlinked
