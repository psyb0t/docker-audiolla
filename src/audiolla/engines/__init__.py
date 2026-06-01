"""Engine factory — build engines keyed by slug from the registry."""

from __future__ import annotations

from typing import Any

from .. import config
from .audio_fingerprint import AudioFingerprintEngine
from .demucs import DemucsEngine
from .ffmpeg_render import FfmpegRenderEngine
from .fx_chain import FxChainEngine
from .librosa_analyze import LibrosaAnalyzeEngine
from .matchering_engine import MatcheringEngine
from .midi_compose import MidiComposeEngine
from .midi_render import MidiRenderEngine
from .pedalboard_chain import PedalboardChainEngine
from .silence_detect import SilenceDetectEngine
from .sox_transform import SoxTransformEngine
from .uvr_separator import UVRSeparatorEngine


def build_engines(registry: dict[str, dict], device: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for slug, entry in registry.items():
        executor = entry.get("executor", "")
        if executor == "demucs":
            out[slug] = DemucsEngine(
                slug=slug,
                entry=entry,
                model_path=config.MODELS_DIR / slug,
                device=device,
            )
            continue
        if executor == "matchering":
            out[slug] = MatcheringEngine(slug=slug, entry=entry)
            continue
        if executor == "pedalboard_chain":
            out[slug] = PedalboardChainEngine(slug=slug, entry=entry)
            continue
        if executor == "librosa_analyze":
            out[slug] = LibrosaAnalyzeEngine(slug=slug, entry=entry)
            continue
        if executor == "sox_transform":
            out[slug] = SoxTransformEngine(slug=slug, entry=entry)
            continue
        if executor == "fx_chain":
            out[slug] = FxChainEngine(slug=slug, entry=entry)
            continue
        if executor == "midi_compose":
            out[slug] = MidiComposeEngine(slug=slug, entry=entry)
            continue
        if executor == "midi_render":
            out[slug] = MidiRenderEngine(slug=slug, entry=entry)
            continue
        if executor == "silence_detect":
            out[slug] = SilenceDetectEngine(slug=slug, entry=entry)
            continue
        if executor == "ffmpeg_render":
            out[slug] = FfmpegRenderEngine(slug=slug, entry=entry)
            continue
        if executor == "audio_fingerprint":
            out[slug] = AudioFingerprintEngine(slug=slug, entry=entry)
            continue
        if executor == "uvr_separator":
            out[slug] = UVRSeparatorEngine(slug=slug, entry=entry)
            continue
        raise ValueError(f"unknown executor {executor!r} for engine {slug!r}")
    return out


# Capability detection via duck-typing — each engine declares its methods;
# the route validates incoming requests match the engine's capabilities.


def is_separation_engine(engine: Any) -> bool:
    return hasattr(engine, "separate")


def is_mastering_engine(engine: Any) -> bool:
    return hasattr(engine, "master_reference") or hasattr(engine, "master_chain")


def is_analysis_engine(engine: Any) -> bool:
    return hasattr(engine, "analyze")


def is_transform_engine(engine: Any) -> bool:
    return hasattr(engine, "transform")


def is_loudness_engine(engine: Any) -> bool:
    return hasattr(engine, "measure_lufs") and hasattr(engine, "normalize_lufs")


def is_fx_engine(engine: Any) -> bool:
    return hasattr(engine, "fx")


def is_midi_compose_engine(engine: Any) -> bool:
    return hasattr(engine, "compose")


def is_midi_render_engine(engine: Any) -> bool:
    return hasattr(engine, "render")


def is_beats_engine(engine: Any) -> bool:
    return hasattr(engine, "beats")


def is_onsets_engine(engine: Any) -> bool:
    return hasattr(engine, "onsets")


def is_melody_engine(engine: Any) -> bool:
    return hasattr(engine, "melody")


def is_segments_engine(engine: Any) -> bool:
    return hasattr(engine, "segments")


def is_silence_engine(engine: Any) -> bool:
    return hasattr(engine, "detect")


def is_ffmpeg_render_engine(engine: Any) -> bool:
    return all(hasattr(engine, m) for m in ("spectrogram", "waveform", "visualize"))


def is_fingerprint_engine(engine: Any) -> bool:
    return hasattr(engine, "compute")


def is_midi_inspect_engine(engine: Any) -> bool:
    return hasattr(engine, "inspect")


def is_midi_transform_engine(engine: Any) -> bool:
    return hasattr(engine, "transform") and hasattr(engine, "compose")


def is_uvr_restore_engine(engine: Any) -> bool:
    return hasattr(engine, "restore")
