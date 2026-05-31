"""Unit tests for MidiRenderEngine validation — the parts that don't
need a real fluidsynth subprocess. End-to-end fluidsynth invocation is
covered by the integration suite."""

from __future__ import annotations

import pytest

from audiolla.engines.midi_render import MidiRenderEngine, MidiRenderError


def _engine() -> MidiRenderEngine:
    return MidiRenderEngine(slug="midi-render", entry={"executor": "midi_render"})


@pytest.mark.asyncio
async def test_render_rejects_empty_midi():
    with pytest.raises(MidiRenderError, match="empty"):
        await _engine().render(b"", "x.mid")


@pytest.mark.asyncio
async def test_render_rejects_non_midi_header():
    """A misuploaded WAV should fail fast with a clear message — saves
    a fluidsynth round-trip + makes the error obvious."""
    with pytest.raises(MidiRenderError, match="Standard MIDI File"):
        await _engine().render(b"RIFF" + b"\x00" * 100, "x.wav")


@pytest.mark.asyncio
async def test_render_rejects_no_default_soundfont(monkeypatch):
    """When AUDIOLLA_SOUNDFONT is empty and no override is passed, the
    engine must refuse with a clear pointer to the config knob."""
    from audiolla.engines import midi_render
    monkeypatch.setattr(midi_render.config, "SOUNDFONT_PATH", "")
    with pytest.raises(MidiRenderError, match="no default SoundFont"):
        # Build a minimal valid MIDI header to skip the earlier guard.
        await _engine().render(b"MThd" + b"\x00" * 100, "x.mid")


@pytest.mark.asyncio
async def test_render_rejects_missing_soundfont_file(monkeypatch):
    """If AUDIOLLA_SOUNDFONT points at a path that doesn't exist, refuse
    rather than handing fluidsynth a bogus path."""
    from audiolla.engines import midi_render
    monkeypatch.setattr(
        midi_render.config, "SOUNDFONT_PATH", "/nope/does-not-exist.sf2",
    )
    with pytest.raises(MidiRenderError, match="is not a file"):
        await _engine().render(b"MThd" + b"\x00" * 100, "x.mid")


@pytest.mark.asyncio
async def test_render_rejects_traversal_in_override(tmp_path, monkeypatch):
    from audiolla.engines import midi_render
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setattr(midi_render.config, "FILES_DIR", files_dir)
    monkeypatch.setattr(midi_render.config, "SOUNDFONT_PATH", "")
    with pytest.raises(MidiRenderError, match="soundfont_path"):
        await _engine().render(
            b"MThd" + b"\x00" * 100, "x.mid",
            soundfont_path="../etc/passwd",
        )


@pytest.mark.asyncio
async def test_render_rejects_override_not_found(tmp_path, monkeypatch):
    from audiolla.engines import midi_render
    files_dir = tmp_path / "files"
    files_dir.mkdir()
    monkeypatch.setattr(midi_render.config, "FILES_DIR", files_dir)
    monkeypatch.setattr(midi_render.config, "SOUNDFONT_PATH", "")
    with pytest.raises(MidiRenderError, match="not found in staging"):
        await _engine().render(
            b"MThd" + b"\x00" * 100, "x.mid",
            soundfont_path="missing.sf2",
        )


@pytest.mark.asyncio
async def test_render_rejects_bad_gain(monkeypatch, tmp_path):
    from audiolla.engines import midi_render
    sf2 = tmp_path / "fake.sf2"
    sf2.write_bytes(b"RIFF" + b"\x00" * 16)
    monkeypatch.setattr(midi_render.config, "SOUNDFONT_PATH", str(sf2))
    with pytest.raises(MidiRenderError, match="gain"):
        await _engine().render(
            b"MThd" + b"\x00" * 100, "x.mid", gain=99.0,
        )


@pytest.mark.asyncio
async def test_render_rejects_unsupported_samplerate(monkeypatch, tmp_path):
    from audiolla.engines import midi_render
    sf2 = tmp_path / "fake.sf2"
    sf2.write_bytes(b"RIFF" + b"\x00" * 16)
    monkeypatch.setattr(midi_render.config, "SOUNDFONT_PATH", str(sf2))
    with pytest.raises(MidiRenderError, match="samplerate"):
        await _engine().render(
            b"MThd" + b"\x00" * 100, "x.mid", samplerate=12345,
        )
