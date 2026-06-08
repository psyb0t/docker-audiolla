"""Engine factory — build engines keyed by slug from the registry.

Rule of thumb for "engine vs audio.py function":

  Engine (subclass of EngineBase, lives in `engines/`)
    Anything stateful, heavy, or with a lifecycle:
    - loads model weights at first use, holds them in memory
    - is evicted from RAM after AUDIOLLA_IDLE_TIMEOUT_SEC
    - serializes requests via its own `_lock`
    - has a slug in `engines.json` so the registry knows about it

  audio.py function (top-level callable in `audio.py`)
    Anything stateless and self-contained:
    - no model weights, no shared mutable state
    - cheap to invoke, no init cost worth caching
    - pure DSP (numpy/scipy/pedalboard/ffmpeg)
    - called directly from server handlers / MCP tools
    - does NOT need a slug in engines.json

When in doubt: if the function would be slow on every call without
caching some loaded resource, it's an engine. Otherwise it's a free
function in audio.py.
"""

from __future__ import annotations

from typing import Any

from .. import config
from .audio_fingerprint import AudioFingerprintEngine
from .basic_pitch_engine import BasicPitchEngine
from .chord_detect_engine import ChordDetectEngine
from .deepfilter_engine import DeepFilterNetEngine
from .demucs import DemucsEngine
from .diarize_pyannote_engine import DiarizeEngine
from .embed_engine import EmbedEngine
from .ffmpeg_render import FfmpegRenderEngine
from .fx_chain import FxChainEngine
from .hpss_engine import HpssEngine
from .librosa_analyze import LibrosaAnalyzeEngine
from .matchering_engine import MatcheringEngine
from .metadata_engine import MetadataEngine
from .midi_compose import MidiComposeEngine
from .music_gen import (
    AudioLDM2Engine,
    MusicGenMediumEngine,
    MusicGenSmallEngine,
    RiffusionEngine,
    StableAudioOpenEngine,
)
from .midi_render import MidiRenderEngine
from .noise_reduce_engine import NoiseReduceEngine
from .pedalboard_chain import PedalboardChainEngine
from .silence_detect import SilenceDetectEngine
from .sox_transform import SoxTransformEngine
from .stretch_engine import StretchEngine
from .tag_engine import TagEngine
from .uvr_separator import UVRSeparatorEngine
from .vad_engine import VADEngine


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
        if executor == "basic_pitch":
            out[slug] = BasicPitchEngine(slug=slug, entry=entry)
            continue
        if executor == "deepfilter":
            out[slug] = DeepFilterNetEngine(slug=slug, entry=entry)
            continue
        if executor == "chord_detect":
            out[slug] = ChordDetectEngine(slug=slug, entry=entry)
            continue
        if executor == "vad":
            out[slug] = VADEngine(slug=slug, entry=entry)
            continue
        if executor == "diarize_pyannote":
            out[slug] = DiarizeEngine(slug=slug, entry=entry)
            continue
        if executor == "stretch":
            out[slug] = StretchEngine(slug=slug, entry=entry)
            continue
        if executor == "ast_tag":
            out[slug] = TagEngine(slug=slug, entry=entry)
            continue
        if executor == "clap_embed":
            out[slug] = EmbedEngine(slug=slug, entry=entry)
            continue
        if executor == "hpss":
            out[slug] = HpssEngine(slug=slug, entry=entry)
            continue
        if executor == "noise_reduce":
            out[slug] = NoiseReduceEngine(slug=slug, entry=entry)
            continue
        if executor == "metadata":
            out[slug] = MetadataEngine(slug=slug, entry=entry)
            continue
        if executor == "stable_audio_open":
            out[slug] = StableAudioOpenEngine(slug=slug, entry=entry)
            continue
        if executor == "musicgen":
            size = entry.get("model_size", "small")
            if size == "medium":
                out[slug] = MusicGenMediumEngine(slug=slug, entry=entry)
            else:
                out[slug] = MusicGenSmallEngine(slug=slug, entry=entry)
            continue
        if executor == "riffusion":
            out[slug] = RiffusionEngine(slug=slug, entry=entry)
            continue
        if executor == "audioldm2":
            out[slug] = AudioLDM2Engine(slug=slug, entry=entry)
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


def is_music_gen_engine(engine: Any) -> bool:
    return hasattr(engine, "generate")


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


def is_basic_pitch_engine(engine: Any) -> bool:
    return hasattr(engine, "to_midi")


def is_deepfilter_engine(engine: Any) -> bool:
    return hasattr(engine, "enhance") and hasattr(engine, "_df_state")


def is_chord_detect_engine(engine: Any) -> bool:
    return hasattr(engine, "detect_chords")


def is_vad_engine(engine: Any) -> bool:
    return hasattr(engine, "detect_voice")


def is_diarize_engine(engine: Any) -> bool:
    return hasattr(engine, "diarize")


def is_stretch_engine(engine: Any) -> bool:
    return hasattr(engine, "stretch")


def is_tag_engine(engine: Any) -> bool:
    return hasattr(engine, "tag")


def is_embed_engine(engine: Any) -> bool:
    return hasattr(engine, "embed")


def is_hpss_engine(engine: Any) -> bool:
    return hasattr(engine, "hpss")


def is_noise_reduce_engine(engine: Any) -> bool:
    return hasattr(engine, "reduce")


def is_classify_engine(engine: Any) -> bool:
    return hasattr(engine, "classify")


def is_metadata_engine(engine: Any) -> bool:
    return hasattr(engine, "read_tags") and hasattr(engine, "write_tags")


def is_pitch_correct_engine(engine: Any) -> bool:
    return hasattr(engine, "pitch_correct")


def is_loop_point_engine(engine: Any) -> bool:
    return hasattr(engine, "loop_point")


def is_drum_pattern_engine(engine: Any) -> bool:
    return hasattr(engine, "drum_pattern")


def is_thumbnail_engine(engine: Any) -> bool:
    return hasattr(engine, "thumbnail")


def is_humanize_engine(engine: Any) -> bool:
    return hasattr(engine, "humanize")
