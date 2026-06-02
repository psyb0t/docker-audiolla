"""Unit tests for VADEngine.

silero-vad and torch are prod-only deps. All imports inside _load_sync()
and the inference path are mocked so these tests run offline in the dev image.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from audiolla.engines.vad_engine import VADEngine, VADError


def _engine() -> VADEngine:
    return VADEngine(slug="silero-vad", entry={"executor": "vad"})


# ── _load_sync ────────────────────────────────────────────────────────────────


def test_load_sync_calls_load_silero_vad():
    mock_model = MagicMock()
    mock_load_silero_vad = MagicMock(return_value=mock_model)
    mock_get_speech_timestamps = MagicMock()
    mock_read_audio = MagicMock()

    mock_silero_vad = MagicMock()
    mock_silero_vad.load_silero_vad = mock_load_silero_vad
    mock_silero_vad.get_speech_timestamps = mock_get_speech_timestamps
    mock_silero_vad.read_audio = mock_read_audio

    with patch.dict("sys.modules", {
        "torch": MagicMock(),
        "silero_vad": mock_silero_vad,
    }):
        eng = _engine()
        result = eng._load_sync()

    mock_load_silero_vad.assert_called_once()
    assert result is mock_model


# ── detect_voice ──────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_voice_returns_speech_segments():
    eng = _engine()
    eng._model = MagicMock()

    fake_audio = MagicMock()
    fake_audio.__len__ = lambda self: 16000
    eng._read_audio = MagicMock(return_value=fake_audio)
    eng._get_speech_timestamps = MagicMock(return_value=[
        {"start": 1.0, "end": 4.5},
    ])

    with patch("audiolla.engines.vad_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        result = await eng.detect_voice(b"audio", "audio.wav")

    assert "speech_segments" in result
    assert "non_speech_segments" in result
    assert "speech_ratio" in result
    assert "duration" in result
    assert "threshold" in result
    assert isinstance(result["speech_segments"], list)


@pytest.mark.asyncio
async def test_detect_voice_empty_audio_returns_zero_ratio():
    eng = _engine()
    eng._model = MagicMock()

    fake_audio = MagicMock()
    fake_audio.__len__ = lambda self: 16000
    eng._read_audio = MagicMock(return_value=fake_audio)
    eng._get_speech_timestamps = MagicMock(return_value=[])

    with patch("audiolla.engines.vad_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        result = await eng.detect_voice(b"audio", "audio.wav")

    assert result["speech_ratio"] == 0.0
    assert result["speech_segments"] == []


@pytest.mark.asyncio
async def test_detect_voice_cleans_up_temp_wav_on_success():
    eng = _engine()
    eng._model = MagicMock()

    fake_audio = MagicMock()
    fake_audio.__len__ = lambda self: 16000
    eng._read_audio = MagicMock(return_value=fake_audio)
    eng._get_speech_timestamps = MagicMock(return_value=[])

    unlinked = []

    with patch("audiolla.engines.vad_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink", side_effect=lambda p: unlinked.append(p)):
        await eng.detect_voice(b"audio", "audio.wav")

    assert "/tmp/fake.wav" in unlinked


@pytest.mark.asyncio
async def test_detect_voice_cleans_up_temp_wav_on_error():
    eng = _engine()
    eng._model = MagicMock()

    fake_audio = MagicMock()
    fake_audio.__len__ = lambda self: 16000
    eng._read_audio = MagicMock(return_value=fake_audio)
    eng._get_speech_timestamps = MagicMock(side_effect=RuntimeError("model crash"))

    unlinked = []

    with patch("audiolla.engines.vad_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink", side_effect=lambda p: unlinked.append(p)):
        with pytest.raises(VADError):
            await eng.detect_voice(b"audio", "audio.wav")

    assert "/tmp/fake.wav" in unlinked


@pytest.mark.asyncio
async def test_detect_voice_passes_threshold_param():
    eng = _engine()
    eng._model = MagicMock()

    fake_audio = MagicMock()
    fake_audio.__len__ = lambda self: 16000
    eng._read_audio = MagicMock(return_value=fake_audio)
    eng._get_speech_timestamps = MagicMock(return_value=[])

    with patch("audiolla.engines.vad_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        await eng.detect_voice(b"audio", "audio.wav", threshold=0.8)

    call_kwargs = eng._get_speech_timestamps.call_args
    assert call_kwargs.kwargs.get("threshold") == 0.8 or \
        (len(call_kwargs.args) > 2 and call_kwargs.args[2] == 0.8)
