"""Unit tests for BasicPitchEngine.

basic-pitch (and its ONNX backend) is only installed in the prod image,
not the dev image. All imports inside _load_sync() and the inference path
are mocked out so these tests run offline without any ML deps.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from audiolla.engines.basic_pitch_engine import BasicPitchEngine, BasicPitchError


def _engine() -> BasicPitchEngine:
    return BasicPitchEngine(slug="basic-pitch", entry={"executor": "basic_pitch"})


# ── _load_sync ────────────────────────────────────────────────────────────────


def test_load_sync_imports_basic_pitch_and_stores_callable():
    mock_predict = MagicMock()
    mock_model_path = "/fake/model"

    with patch.dict("sys.modules", {
        "basic_pitch": MagicMock(ICASSP_2022_MODEL_PATH=mock_model_path),
        "basic_pitch.inference": MagicMock(predict=mock_predict),
    }):
        eng = _engine()
        result = eng._load_sync()

    assert result is mock_predict
    assert eng._predict is mock_predict
    assert eng._model_path == mock_model_path


# ── to_midi ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_to_midi_calls_predict_and_writes_midi():
    """to_midi() should call self._predict with the right kwargs and return
    the MIDI bytes that midi_data.write() produces."""
    fake_midi_bytes = b"MThd" + b"\x00" * 20

    mock_midi_data = MagicMock()
    mock_midi_data.write = MagicMock(side_effect=lambda path: open(path, "wb").write(fake_midi_bytes))

    mock_predict = MagicMock(return_value=(None, mock_midi_data, None))

    eng = _engine()
    eng._model = mock_predict
    eng._predict = mock_predict
    eng._model_path = "/fake/model"

    with patch("audiolla.engines.basic_pitch_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        result = await eng.to_midi(b"audio_bytes", "audio.wav")

    assert result == fake_midi_bytes
    mock_predict.assert_called_once()
    call_kwargs = mock_predict.call_args.kwargs
    assert call_kwargs["onset_threshold"] == 0.5
    assert call_kwargs["frame_threshold"] == 0.3


@pytest.mark.asyncio
async def test_to_midi_passes_custom_thresholds():
    fake_midi_bytes = b"MThd" + b"\x00" * 20
    mock_midi_data = MagicMock()
    mock_midi_data.write = MagicMock(side_effect=lambda path: open(path, "wb").write(fake_midi_bytes))
    mock_predict = MagicMock(return_value=(None, mock_midi_data, None))

    eng = _engine()
    eng._model = mock_predict
    eng._predict = mock_predict
    eng._model_path = "/fake/model"

    with patch("audiolla.engines.basic_pitch_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        await eng.to_midi(
            b"audio_bytes",
            "audio.wav",
            onset_threshold=0.8,
            frame_threshold=0.6,
            minimum_note_length_ms=100.0,
        )

    call_kwargs = mock_predict.call_args.kwargs
    assert call_kwargs["onset_threshold"] == 0.8
    assert call_kwargs["frame_threshold"] == 0.6
    assert call_kwargs["minimum_note_length"] == 100.0


@pytest.mark.asyncio
async def test_to_midi_wraps_predict_exception_in_basic_pitch_error():
    mock_predict = MagicMock(side_effect=RuntimeError("ONNX inference failed"))

    eng = _engine()
    eng._model = mock_predict
    eng._predict = mock_predict
    eng._model_path = "/fake/model"

    with patch("audiolla.engines.basic_pitch_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        with pytest.raises(BasicPitchError, match="basic-pitch inference failed"):
            await eng.to_midi(b"audio_bytes", "audio.wav")


@pytest.mark.asyncio
async def test_to_midi_cleans_up_temp_files_on_success(tmp_path):
    fake_midi_bytes = b"MThd" + b"\x00" * 20
    mock_midi_data = MagicMock()
    mock_midi_data.write = MagicMock(side_effect=lambda path: open(path, "wb").write(fake_midi_bytes))
    mock_predict = MagicMock(return_value=(None, mock_midi_data, None))

    eng = _engine()
    eng._model = mock_predict
    eng._predict = mock_predict
    eng._model_path = str(tmp_path / "model")

    wav_path = str(tmp_path / "input.wav")
    open(wav_path, "wb").write(b"fake_wav")

    unlinked = []

    def _fake_unlink(p):
        unlinked.append(p)

    with patch("audiolla.engines.basic_pitch_engine.to_wav_float32", return_value=wav_path), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink", side_effect=_fake_unlink):
        await eng.to_midi(b"audio_bytes", "audio.wav")

    # Both the wav and the midi temp file must be unlinked.
    assert wav_path in unlinked
    assert len(unlinked) == 2


@pytest.mark.asyncio
async def test_to_midi_cleans_up_temp_files_on_error(tmp_path):
    mock_predict = MagicMock(side_effect=RuntimeError("boom"))

    eng = _engine()
    eng._model = mock_predict
    eng._predict = mock_predict
    eng._model_path = str(tmp_path / "model")

    wav_path = str(tmp_path / "input.wav")

    unlinked = []

    def _fake_unlink(p):
        unlinked.append(p)

    with patch("audiolla.engines.basic_pitch_engine.to_wav_float32", return_value=wav_path), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink", side_effect=_fake_unlink):
        with pytest.raises(BasicPitchError):
            await eng.to_midi(b"audio_bytes", "audio.wav")

    assert wav_path in unlinked
