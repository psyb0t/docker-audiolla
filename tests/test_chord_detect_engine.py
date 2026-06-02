"""Unit tests for ChordDetectEngine.

librosa and numpy are prod-only deps. All imports inside _load_sync() and
the inference path are mocked so these tests run offline in the dev image.
"""

from __future__ import annotations

import re
from unittest.mock import MagicMock, patch

import pytest

from audiolla.engines.chord_detect_engine import ChordDetectEngine, ChordDetectError


def _engine() -> ChordDetectEngine:
    return ChordDetectEngine(slug="chord-detect", entry={"executor": "chord_detect"})


def _make_np_mock() -> MagicMock:
    """Return a mock numpy that returns numeric values from array ops."""
    mock_np = MagicMock()

    # np.array(x) → just echo back x as a MagicMock
    mock_np.array.return_value = MagicMock()

    # np.inf → a large float so comparisons work
    mock_np.inf = float("inf")

    # np.zeros(12) → a MagicMock (used for template vectors)
    mock_np.zeros.return_value = MagicMock()

    # np.roll, np.corrcoef, np.dot all return numeric mocks.
    # corrcoef returns a 2x2-like: code accesses [0, 1] as a tuple key.
    corr_matrix = MagicMock()
    corr_matrix.__getitem__ = lambda self, key: 0.7
    mock_np.corrcoef.return_value = corr_matrix
    mock_np.dot.return_value = 0.5
    mock_np.clip.return_value = 0.9
    mock_np.mean.return_value = 0.5
    mock_np.arange.return_value = list(range(10))
    mock_np.roll.return_value = MagicMock()

    return mock_np


def _make_mock_librosa(n_frames: int = 10, duration: float = 8.0) -> MagicMock:
    # Build a chroma array-like: shape (12, n_frames)
    mock_chroma = MagicMock()
    mock_chroma.shape = (12, n_frames)

    # mean(axis=1) returns a MagicMock column vector
    mock_chroma.mean.return_value = MagicMock()

    # chroma[:, i] → a per-frame MagicMock (returns a MagicMock for any index)
    mock_chroma.__getitem__ = MagicMock(return_value=MagicMock())

    # Build a fake y array-like whose len() returns a real int so duration works.
    fake_y = MagicMock()
    type(fake_y).__len__ = lambda self: 22050 * 8  # type: ignore[assignment]

    mock_librosa = MagicMock()
    mock_librosa.__version__ = "0.10.0"
    mock_librosa.load.return_value = (fake_y, 22050)
    mock_librosa.feature.chroma_cqt.return_value = mock_chroma
    mock_librosa.frames_to_time.return_value = [i * duration / n_frames for i in range(n_frames)]
    return mock_librosa


# ── _load_sync ────────────────────────────────────────────────────────────────


def test_load_sync_imports_librosa_and_numpy():
    mock_librosa = MagicMock()
    mock_librosa.__version__ = "0.10.0"
    mock_np = MagicMock()

    with patch.dict("sys.modules", {
        "librosa": mock_librosa,
        "librosa.feature": mock_librosa.feature,
        "numpy": mock_np,
    }):
        eng = _engine()
        result = eng._load_sync()

    assert result is not None
    assert eng._librosa is mock_librosa
    assert eng._np is mock_np


# ── detect_chords ─────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_detect_chords_returns_key_and_chords():
    mock_librosa = _make_mock_librosa()
    mock_np = _make_np_mock()

    eng = _engine()
    eng._model = mock_librosa  # bypass get_model() → _load_sync()
    eng._librosa = mock_librosa
    eng._np = mock_np

    with patch("audiolla.engines.chord_detect_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        result = await eng.detect_chords(b"audio", "audio.wav")

    assert "key" in result
    assert "key_confidence" in result
    assert "chords" in result
    assert "duration" in result
    assert isinstance(result["chords"], list)


@pytest.mark.asyncio
async def test_detect_chords_key_is_valid_string():
    mock_librosa = _make_mock_librosa()
    mock_np = _make_np_mock()

    # Force corrcoef to return a high correlation for C major (index 0, major)
    # by making it increment to a stable float value per call.
    call_count = [0]

    def _corrcoef_side_effect(a, b):
        call_count[0] += 1
        matrix = MagicMock()
        # Return a high correlation for the first call (C major → index 0).
        # Code accesses [0, 1] as a tuple key.
        val = 0.95 if call_count[0] == 1 else 0.5
        matrix.__getitem__ = lambda self, key: val
        return matrix

    mock_np.corrcoef.side_effect = _corrcoef_side_effect

    eng = _engine()
    eng._model = mock_librosa  # bypass get_model() → _load_sync()
    eng._librosa = mock_librosa
    eng._np = mock_np

    with patch("audiolla.engines.chord_detect_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        result = await eng.detect_chords(b"audio", "audio.wav")

    assert re.match(r"^[A-G]#? (major|minor)$", result["key"]), \
        f"key '{result['key']}' does not match '<note> major/minor'"


@pytest.mark.asyncio
async def test_detect_chords_cleans_up_temp_wav_on_success():
    mock_librosa = _make_mock_librosa()
    mock_np = _make_np_mock()

    eng = _engine()
    eng._model = mock_librosa  # bypass get_model() → _load_sync()
    eng._librosa = mock_librosa
    eng._np = mock_np

    unlinked = []

    with patch("audiolla.engines.chord_detect_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink", side_effect=lambda p: unlinked.append(p)):
        await eng.detect_chords(b"audio", "audio.wav")

    assert "/tmp/fake.wav" in unlinked


@pytest.mark.asyncio
async def test_detect_chords_cleans_up_temp_wav_on_error():
    mock_librosa = MagicMock()
    mock_librosa.__version__ = "0.10.0"
    mock_librosa.load.side_effect = RuntimeError("librosa load failed")
    mock_np = _make_np_mock()

    eng = _engine()
    eng._model = mock_librosa  # bypass get_model() → _load_sync()
    eng._librosa = mock_librosa
    eng._np = mock_np

    unlinked = []

    with patch("audiolla.engines.chord_detect_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink", side_effect=lambda p: unlinked.append(p)):
        with pytest.raises(ChordDetectError):
            await eng.detect_chords(b"audio", "audio.wav")

    assert "/tmp/fake.wav" in unlinked


@pytest.mark.asyncio
async def test_detect_chords_wraps_exception_in_chord_detect_error():
    mock_librosa = MagicMock()
    mock_librosa.__version__ = "0.10.0"
    mock_librosa.load.side_effect = ValueError("unexpected shape")
    mock_np = _make_np_mock()

    eng = _engine()
    eng._model = mock_librosa  # bypass get_model() → _load_sync()
    eng._librosa = mock_librosa
    eng._np = mock_np

    with patch("audiolla.engines.chord_detect_engine.to_wav_float32", return_value="/tmp/fake.wav"), \
         patch("os.path.exists", return_value=True), \
         patch("os.unlink"):
        with pytest.raises(ChordDetectError, match="chord detection failed"):
            await eng.detect_chords(b"audio", "audio.wav")
