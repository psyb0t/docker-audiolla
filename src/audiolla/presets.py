"""Preset registry — curated server-side pipelines loaded from YAML.

Presets live as ``.yaml`` files in the ``presets/`` directory at the repo
root (configurable via AUDIOLLA_PRESETS_DIR). Each file defines a name,
description, and a list of pipeline steps. The loader reads them at app
startup; ``/v1/presets/{name}`` runs the pipeline against an input file.

A preset's steps follow the same shape as the ``/v1/pipeline`` body — see
``pipeline.OPS`` for the available op slugs and their params.

Example file (``presets/podcast-cleanup.yaml``):

    name: podcast-cleanup
    description: Voice enhance + de-ess + normalize to -16 LUFS
    steps:
      - op: enhance
        params: {engine: deepfilter}
      - op: deess
        params: {threshold_db: -18, ratio: 4}
      - op: normalize
        params: {target_lufs: -16}
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("audiolla.presets")


class PresetError(Exception):
    """Preset file malformed or preset name unknown."""


class Preset:
    """A loaded preset: name, description, list of steps."""

    __slots__ = ("name", "description", "steps", "source_path")

    def __init__(self, name: str, description: str, steps: list[dict],
                 source_path: Path | None = None) -> None:
        self.name = name
        self.description = description
        self.steps = steps
        self.source_path = source_path

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": self.steps,
        }


def _validate_preset_dict(data: Any, *, source: str) -> Preset:
    if not isinstance(data, dict):
        raise PresetError(f"{source}: preset must be a YAML mapping")
    name = data.get("name")
    description = data.get("description", "")
    steps = data.get("steps")
    if not isinstance(name, str) or not name:
        raise PresetError(f"{source}: 'name' is required and must be a non-empty string")
    if not isinstance(description, str):
        raise PresetError(f"{source}: 'description' must be a string")
    if not isinstance(steps, list) or not steps:
        raise PresetError(f"{source}: 'steps' is required and must be a non-empty list")
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise PresetError(f"{source}: steps[{i}] must be a mapping")
        if not isinstance(step.get("op"), str):
            raise PresetError(f"{source}: steps[{i}].op must be a string")
        params = step.get("params", {})
        if not isinstance(params, dict):
            raise PresetError(f"{source}: steps[{i}].params must be a mapping")
    return Preset(name=name, description=description, steps=steps)


def load_presets(presets_dir: Path) -> dict[str, Preset]:
    """Read every ``*.yaml`` / ``*.yml`` file in ``presets_dir`` into a name→Preset
    map. Malformed files are logged and skipped, not fatal — bad presets
    shouldn't block server startup. Returns an empty dict if the directory
    doesn't exist."""
    import yaml  # noqa: PLC0415

    out: dict[str, Preset] = {}
    if not presets_dir.is_dir():
        log.info("presets dir %s does not exist; no presets loaded", presets_dir)
        return out

    for path in sorted(presets_dir.iterdir()):
        if path.suffix not in (".yaml", ".yml"):
            continue
        try:
            with path.open("r", encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            preset = _validate_preset_dict(data, source=str(path))
        except (yaml.YAMLError, PresetError) as exc:
            log.warning("skipping malformed preset %s: %s", path.name, exc)
            continue
        preset.source_path = path
        if preset.name in out:
            log.warning(
                "duplicate preset name %r (existing source=%s, new source=%s); "
                "keeping the first",
                preset.name, out[preset.name].source_path, path,
            )
            continue
        out[preset.name] = preset

    log.info("loaded %d preset(s) from %s", len(out), presets_dir)
    return out
