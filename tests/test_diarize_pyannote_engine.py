"""Unit tests for DiarizeEngine (pyannote.audio).

pyannote.audio and torch are prod-only deps. All imports inside _load_sync()
and the inference path are mocked so these tests run offline in the dev image.
"""

from __future__ import annotations

import os
from unittest.mock import MagicMock, patch

import pytest

from audiolla.engines.diarize_pyannote_engine import DiarizeEngine, DiarizeError


def _engine() -> DiarizeEngine:
    return DiarizeEngine(slug="pyannote", entry={"executor": "diarize_pyannote"})


def _mock_annotation() -> MagicMock:
    mock_turn_0 = MagicMock()
    mock_turn_0.start = 0.0
    mock_turn_0.end = 5.3

    mock_turn_1 = MagicMock()
    mock_turn_1.start = 5.3
    mock_turn_1.end = 12.1

    mock_annotation = MagicMock()
    mock_annotation.itertracks.return_value = [
        (mock_turn_0, None, "SPEAKER_00"),
        (mock_turn_1, None, "SPEAKER_01"),
    ]
    return mock_annotation


# ── _load_sync ────────────────────────────────────────────────────────────────


def test_load_sync_raises_without_hf_token():
    mock_pyannote_audio = MagicMock()
    with patch.dict("sys.modules", {
        "pyannote": MagicMock(),
        "pyannote.audio": mock_pyannote_audio,
    }), patch.dict(os.environ, {"HUGGINGFACE_TOKEN": ""}, clear=False):
        eng = _engine()
        with pytest.raises(DiarizeError, match="HUGGINGFACE_TOKEN"):
            eng._load_sync()


def test_load_sync_calls_pipeline_from_pretrained():
    mock_pipeline_instance = MagicMock()
    mock_pipeline_cls = MagicMock()
    mock_pipeline_cls.from_pretrained.return_value = mock_pipeline_instance

    mock_pyannote_audio = MagicMock()
    mock_pyannote_audio.Pipeline = mock_pipeline_cls

    with patch.dict("sys.modules", {
        "pyannote": MagicMock(),
        "pyannote.audio": mock_pyannote_audio,
    }), patch.dict(os.environ, {"HUGGINGFACE_TOKEN": "fake-token"}):
        eng = _engine()
        result = eng._load_sync()

    mock_pipeline_cls.from_pretrained.assert_called_once_with(
        "pyannote/speaker-diarization-3.1",
        use_auth_token="fake-token",
    )
    assert result is mock_pipeline_instance


# ── diarize ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_diarize_returns_segments_and_speakers():
    eng = _engine()
    annotation = _mock_annotation()
    eng._pipeline = MagicMock(return_value=annotation)
    eng._model = eng._pipeline  # bypass get_model() → _load_sync()

    with patch("audiolla.engines.diarize_pyannote_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        result = await eng.diarize(b"audio", "audio.wav")

    assert isinstance(result["segments"], list)
    assert result["num_speakers"] == 2
    assert result["speakers"] == ["SPEAKER_00", "SPEAKER_01"]
    assert result["duration"] > 0


@pytest.mark.asyncio
async def test_diarize_segments_have_correct_fields():
    eng = _engine()
    annotation = _mock_annotation()
    eng._pipeline = MagicMock(return_value=annotation)
    eng._model = eng._pipeline  # bypass get_model() → _load_sync()

    with patch("audiolla.engines.diarize_pyannote_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        result = await eng.diarize(b"audio", "audio.wav")

    for seg in result["segments"]:
        assert "speaker" in seg
        assert "start_sec" in seg
        assert "end_sec" in seg
        assert "duration_sec" in seg


@pytest.mark.asyncio
async def test_diarize_passes_num_speakers_param():
    eng = _engine()
    annotation = _mock_annotation()
    mock_pipeline = MagicMock(return_value=annotation)
    eng._pipeline = mock_pipeline
    eng._model = mock_pipeline  # bypass get_model() → _load_sync()

    with patch("audiolla.engines.diarize_pyannote_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        await eng.diarize(b"audio", "audio.wav", num_speakers=2)

    call_kwargs = mock_pipeline.call_args.kwargs
    assert call_kwargs.get("num_speakers") == 2


@pytest.mark.asyncio
async def test_diarize_passes_min_max_speakers():
    eng = _engine()
    annotation = _mock_annotation()
    mock_pipeline = MagicMock(return_value=annotation)
    eng._pipeline = mock_pipeline
    eng._model = mock_pipeline  # bypass get_model() → _load_sync()

    with patch("audiolla.engines.diarize_pyannote_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        await eng.diarize(b"audio", "audio.wav", min_speakers=1, max_speakers=3)

    call_kwargs = mock_pipeline.call_args.kwargs
    assert call_kwargs.get("min_speakers") == 1
    assert call_kwargs.get("max_speakers") == 3


@pytest.mark.asyncio
async def test_diarize_cleans_up_temp_wav_on_success():
    eng = _engine()
    annotation = _mock_annotation()
    eng._pipeline = MagicMock(return_value=annotation)
    eng._model = eng._pipeline  # bypass get_model() → _load_sync()

    unlinked = []

    with patch("audiolla.engines.diarize_pyannote_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink", side_effect=lambda p: unlinked.append(p)):
        await eng.diarize(b"audio", "audio.wav")

    assert "/tmp/fake.wav" in unlinked


@pytest.mark.asyncio
async def test_diarize_cleans_up_temp_wav_on_error():
    eng = _engine()
    eng._pipeline = MagicMock(side_effect=RuntimeError("pipeline crash"))
    eng._model = eng._pipeline  # bypass get_model() → _load_sync()

    unlinked = []

    with patch("audiolla.engines.diarize_pyannote_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink", side_effect=lambda p: unlinked.append(p)):
        with pytest.raises(DiarizeError):
            await eng.diarize(b"audio", "audio.wav")

    assert "/tmp/fake.wav" in unlinked
