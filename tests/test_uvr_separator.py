"""Unit tests for UVRSeparatorEngine.

Heavy deps (audio_separator) are NOT in the dev image — all imports
inside _load_sync() and the inference methods are mocked.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from audiolla.engines.uvr_separator import (
    UVRSeparatorEngine,
    UVRSeparatorError,
    _extract_stem_name,
    _find_stem_file,
)


def _engine(primary_stem: str | None = None) -> UVRSeparatorEngine:
    entry: dict = {"executor": "uvr_separator", "model": "model.ckpt"}
    if primary_stem is not None:
        entry["primary_stem"] = primary_stem
    return UVRSeparatorEngine(slug="uvr-dereverb", entry=entry)


# ── _load_sync ────────────────────────────────────────────────────────────────


def test_load_sync_creates_separator_and_loads_model(tmp_path, monkeypatch):
    monkeypatch.setattr("audiolla.engines.uvr_separator.config.UVR_MODELS_DIR", str(tmp_path))

    mock_sep_cls = MagicMock()
    mock_sep_instance = MagicMock()
    mock_sep_cls.return_value = mock_sep_instance

    with patch.dict("sys.modules", {"audio_separator": MagicMock(), "audio_separator.separator": MagicMock(Separator=mock_sep_cls)}):
        eng = _engine(primary_stem="No Reverb")
        result = eng._load_sync()

    mock_sep_cls.assert_called_once()
    mock_sep_instance.load_model.assert_called_once_with("model.ckpt")
    assert result is mock_sep_instance


# ── restore ───────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_restore_calls_separate_and_encodes(tmp_path, monkeypatch):
    """restore() should write input, call model.separate, encode the output."""
    monkeypatch.setattr("audiolla.engines.uvr_separator.config.UVR_MODELS_DIR", str(tmp_path))

    # Fake output WAV file that _restore_sync will find.
    fake_wav = str(tmp_path / "out_(No Reverb).wav")
    with open(fake_wav, "wb") as fh:
        fh.write(b"RIFF" + b"\x00" * 100)

    mock_sep = MagicMock()
    mock_sep.separate.return_value = [fake_wav]

    eng = _engine(primary_stem="No Reverb")
    eng._model = mock_sep

    with patch("audiolla.engines.uvr_separator.encode_audio", return_value=(b"encoded_audio", "wav")):
        result = await eng.restore(b"input_audio", "audio.wav")

    assert result == b"encoded_audio"
    mock_sep.separate.assert_called_once()


@pytest.mark.asyncio
async def test_restore_raises_when_no_output_files(tmp_path, monkeypatch):
    monkeypatch.setattr("audiolla.engines.uvr_separator.config.UVR_MODELS_DIR", str(tmp_path))

    mock_sep = MagicMock()
    mock_sep.separate.return_value = []

    eng = _engine()
    eng._model = mock_sep

    with pytest.raises(UVRSeparatorError, match="no output files"):
        await eng.restore(b"input", "audio.wav")


# ── separate ──────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_separate_returns_dict_of_stem_bytes(tmp_path, monkeypatch):
    monkeypatch.setattr("audiolla.engines.uvr_separator.config.UVR_MODELS_DIR", str(tmp_path))

    vocals_wav = str(tmp_path / "out_(Vocals).wav")
    instru_wav = str(tmp_path / "out_(Instrumental).wav")
    for p in (vocals_wav, instru_wav):
        with open(p, "wb") as fh:
            fh.write(b"RIFF" + b"\x00" * 50)

    mock_sep = MagicMock()
    mock_sep.separate.return_value = [vocals_wav, instru_wav]

    eng = UVRSeparatorEngine(
        slug="uvr-vocal", entry={"executor": "uvr_separator", "model": "model.ckpt"}
    )
    eng._model = mock_sep

    with patch(
        "audiolla.engines.uvr_separator.encode_audio",
        side_effect=lambda path, fmt: (b"bytes_" + path.encode()[-5:], fmt),
    ):
        result = await eng.separate(b"input", "audio.wav")

    assert "Vocals" in result
    assert "Instrumental" in result


@pytest.mark.asyncio
async def test_separate_raises_when_no_recognisable_stems(tmp_path, monkeypatch):
    monkeypatch.setattr("audiolla.engines.uvr_separator.config.UVR_MODELS_DIR", str(tmp_path))

    unrecognised_wav = str(tmp_path / "out_nostem.wav")
    with open(unrecognised_wav, "wb") as fh:
        fh.write(b"RIFF" + b"\x00" * 50)

    mock_sep = MagicMock()
    mock_sep.separate.return_value = [unrecognised_wav]

    eng = _engine()
    eng._model = mock_sep

    with pytest.raises(UVRSeparatorError, match="no recognisable stems"):
        await eng.separate(b"input", "audio.wav")


@pytest.mark.asyncio
async def test_separate_filters_requested_stems(tmp_path, monkeypatch):
    monkeypatch.setattr("audiolla.engines.uvr_separator.config.UVR_MODELS_DIR", str(tmp_path))

    vocals_wav = str(tmp_path / "out_(Vocals).wav")
    instru_wav = str(tmp_path / "out_(Instrumental).wav")
    for p in (vocals_wav, instru_wav):
        with open(p, "wb") as fh:
            fh.write(b"RIFF" + b"\x00" * 50)

    mock_sep = MagicMock()
    mock_sep.separate.return_value = [vocals_wav, instru_wav]

    eng = _engine()
    eng._model = mock_sep

    with patch(
        "audiolla.engines.uvr_separator.encode_audio",
        side_effect=lambda path, fmt: (b"bytes", fmt),
    ):
        result = await eng.separate(b"input", "audio.wav", stems=["Vocals"])

    assert "Vocals" in result
    assert "Instrumental" not in result


# ── helper functions ──────────────────────────────────────────────────────────


def test_extract_stem_name_parses_bracket_name():
    assert _extract_stem_name("/tmp/track_(Vocals).wav") == "Vocals"
    assert _extract_stem_name("/tmp/track_(No Reverb).flac") == "No Reverb"


def test_extract_stem_name_returns_none_when_no_bracket():
    assert _extract_stem_name("/tmp/track_plain.wav") is None


def test_find_stem_file_finds_correct_file():
    files = ["/tmp/out_(Vocals).wav", "/tmp/out_(Instrumental).wav"]
    assert _find_stem_file(files, "Vocals") == "/tmp/out_(Vocals).wav"
    assert _find_stem_file(files, "Instrumental") == "/tmp/out_(Instrumental).wav"


def test_find_stem_file_returns_none_when_not_found():
    files = ["/tmp/out_(Vocals).wav"]
    assert _find_stem_file(files, "Bass") is None
