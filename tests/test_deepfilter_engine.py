"""Unit tests for DeepFilterNetEngine.

The deepfilternet library (torch, soundfile) is prod-only.  All imports
inside _load_sync() and _enhance_sync() are mocked so these tests run
offline in the dev image.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from audiolla.engines.deepfilter_engine import DeepFilterError, DeepFilterNetEngine


def _engine() -> DeepFilterNetEngine:
    return DeepFilterNetEngine(slug="deepfilter", entry={"executor": "deepfilter"})


# ── _load_sync ────────────────────────────────────────────────────────────────


def test_load_sync_calls_init_df_and_stores_state():
    mock_model = MagicMock()
    mock_df_state = MagicMock()
    mock_df_state.sr.return_value = 48000
    mock_enhance_fn = MagicMock()
    mock_init_df = MagicMock(return_value=(mock_model, mock_df_state, None))

    with patch.dict("sys.modules", {
        "df": MagicMock(),
        "df.enhance": MagicMock(enhance=mock_enhance_fn, init_df=mock_init_df),
    }):
        eng = _engine()
        result = eng._load_sync()

    mock_init_df.assert_called_once()
    assert result is mock_model
    assert eng._model is mock_model
    assert eng._df_state is mock_df_state
    assert eng._enhance is mock_enhance_fn


# ── enhance ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_enhance_calls_enhance_and_returns_encoded_audio(tmp_path):
    """enhance() should invoke the DF enhance fn and encode the output."""
    mock_model = MagicMock()
    mock_df_state = MagicMock()
    mock_df_state.sr.return_value = 48000

    # Mock soundfile.read → returns (audio_array, sr)
    mock_audio = MagicMock()
    mock_audio.T = MagicMock()

    # Mock torch.from_numpy → returns a tensor-like
    mock_tensor = MagicMock()
    mock_tensor.numpy.return_value.T = mock_audio

    mock_enhance_fn = MagicMock(return_value=mock_tensor)

    eng = _engine()
    eng._model = mock_model
    eng._df_state = mock_df_state
    eng._enhance = mock_enhance_fn

    wav_path = str(tmp_path / "input.wav")
    open(wav_path, "wb").write(b"fake_wav")

    out_wav = str(tmp_path / "out.wav")
    open(out_wav, "wb").write(b"RIFF" + b"\x00" * 50)

    with patch("audiolla.engines.deepfilter_engine.to_wav_float32", return_value=wav_path), \
         patch("audiolla.engines.deepfilter_engine.encode_audio", return_value=(b"encoded", "wav")), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"), \
         patch("os.close"), \
         patch.dict("sys.modules", {
             "soundfile": MagicMock(read=MagicMock(return_value=(mock_audio, 48000))),
             "torch": MagicMock(from_numpy=MagicMock(return_value=mock_tensor)),
         }), \
         patch("tempfile.mkstemp", return_value=(999, out_wav)):
        result = await eng.enhance(b"audio_bytes", "audio.wav")

    assert result == b"encoded"


@pytest.mark.asyncio
async def test_enhance_wraps_runtime_error_in_deep_filter_error(tmp_path):
    mock_model = MagicMock()
    mock_df_state = MagicMock()
    mock_df_state.sr.return_value = 48000

    eng = _engine()
    eng._model = mock_model
    eng._df_state = mock_df_state
    eng._enhance = MagicMock(side_effect=RuntimeError("CUDA OOM"))

    wav_path = str(tmp_path / "input.wav")
    open(wav_path, "wb").write(b"fake_wav")

    with patch("audiolla.engines.deepfilter_engine.to_wav_float32", return_value=wav_path), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"), \
         patch.dict("sys.modules", {
             "soundfile": MagicMock(read=MagicMock(return_value=(MagicMock(), 48000))),
             "torch": MagicMock(from_numpy=MagicMock(return_value=MagicMock())),
         }):
        with pytest.raises(DeepFilterError, match="DeepFilterNet inference failed"):
            await eng.enhance(b"audio_bytes", "audio.wav")


@pytest.mark.asyncio
async def test_enhance_cleans_up_temp_files_on_success(tmp_path):
    mock_model = MagicMock()
    mock_df_state = MagicMock()
    mock_df_state.sr.return_value = 48000

    mock_audio = MagicMock()
    mock_tensor = MagicMock()
    mock_tensor.numpy.return_value.T = mock_audio
    mock_enhance_fn = MagicMock(return_value=mock_tensor)

    eng = _engine()
    eng._model = mock_model
    eng._df_state = mock_df_state
    eng._enhance = mock_enhance_fn

    wav_path = str(tmp_path / "input.wav")
    out_wav = str(tmp_path / "out.wav")
    open(wav_path, "wb").write(b"fake")
    open(out_wav, "wb").write(b"RIFF" + b"\x00" * 50)

    unlinked = []

    with patch("audiolla.engines.deepfilter_engine.to_wav_float32", return_value=wav_path), \
         patch("audiolla.engines.deepfilter_engine.encode_audio", return_value=(b"enc", "wav")), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink", side_effect=lambda p: unlinked.append(p)), \
         patch("os.close"), \
         patch.dict("sys.modules", {
             "soundfile": MagicMock(
                 read=MagicMock(return_value=(mock_audio, 48000)),
                 write=MagicMock(),
             ),
             "torch": MagicMock(from_numpy=MagicMock(return_value=mock_tensor)),
         }), \
         patch("tempfile.mkstemp", return_value=(999, out_wav)):
        await eng.enhance(b"audio_bytes", "audio.wav")

    assert wav_path in unlinked
    assert out_wav in unlinked


# ── is_deepfilter_engine duck-typing ─────────────────────────────────────────


def test_engine_has_required_attributes():
    from audiolla.engines import is_deepfilter_engine

    eng = _engine()
    # Before load, _df_state is not present → should fail the duck-type check.
    assert not is_deepfilter_engine(eng)

    # After load (simulated by setting the attribute), it should pass.
    eng._df_state = MagicMock()
    assert is_deepfilter_engine(eng)
