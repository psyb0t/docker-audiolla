"""Unit tests for audiolla.presets — YAML loader + validation."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from audiolla.presets import Preset, PresetError, _validate_preset_dict, load_presets


# ── validation ───────────────────────────────────────────────────────────────


def test_validate_rejects_non_mapping():
    with pytest.raises(PresetError, match="must be a YAML mapping"):
        _validate_preset_dict("just a string", source="x.yaml")


def test_validate_requires_name():
    with pytest.raises(PresetError, match="'name' is required"):
        _validate_preset_dict({"steps": [{"op": "trim"}]}, source="x.yaml")


def test_validate_requires_steps():
    with pytest.raises(PresetError, match="'steps' is required"):
        _validate_preset_dict({"name": "p", "description": "d"}, source="x.yaml")


def test_validate_rejects_empty_steps_list():
    with pytest.raises(PresetError, match="'steps' is required"):
        _validate_preset_dict(
            {"name": "p", "description": "d", "steps": []}, source="x.yaml",
        )


def test_validate_rejects_step_with_non_string_op():
    with pytest.raises(PresetError, match=r"steps\[0\].op must be a string"):
        _validate_preset_dict(
            {"name": "p", "description": "d", "steps": [{"op": 123}]},
            source="x.yaml",
        )


def test_validate_rejects_non_dict_params():
    with pytest.raises(PresetError, match=r"steps\[0\].params must be a mapping"):
        _validate_preset_dict(
            {"name": "p", "description": "d", "steps": [{"op": "trim", "params": "x"}]},
            source="x.yaml",
        )


def test_validate_accepts_minimal_preset():
    preset = _validate_preset_dict(
        {"name": "p", "description": "d", "steps": [{"op": "reverse"}]},
        source="x.yaml",
    )
    assert isinstance(preset, Preset)
    assert preset.name == "p"
    assert preset.description == "d"
    assert preset.steps == [{"op": "reverse"}]


# ── filesystem loader ────────────────────────────────────────────────────────


def test_load_presets_empty_dir(tmp_path: Path):
    presets = load_presets(tmp_path)
    assert presets == {}


def test_load_presets_missing_dir_returns_empty(tmp_path: Path):
    presets = load_presets(tmp_path / "does-not-exist")
    assert presets == {}


def test_load_presets_reads_valid_yaml(tmp_path: Path):
    (tmp_path / "good.yaml").write_text(textwrap.dedent("""
        name: my-preset
        description: A test preset
        steps:
          - op: reverse
          - op: normalize
            params:
              target_lufs: -14.0
    """).strip())
    presets = load_presets(tmp_path)
    assert "my-preset" in presets
    p = presets["my-preset"]
    assert p.name == "my-preset"
    assert len(p.steps) == 2
    assert p.steps[1]["params"]["target_lufs"] == -14.0


def test_load_presets_skips_malformed_yaml(tmp_path: Path, caplog):
    (tmp_path / "broken.yaml").write_text("this: is: not: valid: yaml: ::")
    (tmp_path / "good.yaml").write_text(textwrap.dedent("""
        name: good
        steps:
          - op: reverse
    """).strip())
    presets = load_presets(tmp_path)
    # Malformed file skipped, good one loaded
    assert "good" in presets
    assert "broken" not in presets


def test_load_presets_ignores_non_yaml_files(tmp_path: Path):
    (tmp_path / "notes.txt").write_text("ignored")
    (tmp_path / "README.md").write_text("# header")
    (tmp_path / "p.yaml").write_text(textwrap.dedent("""
        name: p
        steps:
          - op: reverse
    """).strip())
    presets = load_presets(tmp_path)
    assert list(presets) == ["p"]


def test_load_presets_handles_duplicate_names(tmp_path: Path):
    (tmp_path / "a.yaml").write_text(textwrap.dedent("""
        name: dup
        description: first
        steps:
          - op: reverse
    """).strip())
    (tmp_path / "b.yaml").write_text(textwrap.dedent("""
        name: dup
        description: second
        steps:
          - op: reverse
    """).strip())
    presets = load_presets(tmp_path)
    # First wins (sorted iteration = a.yaml before b.yaml)
    assert presets["dup"].description == "first"


def test_load_real_repo_presets():
    """Sanity check against the actual presets shipped in the repo."""
    repo_presets = Path(__file__).resolve().parent.parent / "presets"
    if not repo_presets.is_dir():
        pytest.skip("repo presets dir not present in this checkout")
    presets = load_presets(repo_presets)
    assert "podcast-cleanup" in presets
    assert "master-for-spotify" in presets
    assert "vocal-cleanup" in presets
    for p in presets.values():
        assert p.description
        assert len(p.steps) >= 1
