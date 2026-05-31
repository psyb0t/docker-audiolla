"""Engine factory — build engines keyed by slug from the registry."""

from __future__ import annotations

from typing import Any

from .. import config
from .demucs import DemucsEngine
from .matchering_engine import MatcheringEngine
from .pedalboard_chain import PedalboardChainEngine
from .librosa_analyze import LibrosaAnalyzeEngine
from .sox_transform import SoxTransformEngine


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
