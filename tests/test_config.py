"""Unit tests for audiolla.config — env parsing + load_registry() validation.

Pure-python paths only; no ML deps required. Each test reloads the config
module under a fresh env so tests don't leak state.
"""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


def _reload_config(monkeypatch, engines_path: Path, **env: str):
    """Reload audiolla.config with a specific ENGINES_FILE + env vars."""
    monkeypatch.setenv("AUDIOLLA_ENGINES_FILE", str(engines_path))
    for var in ("AUDIOLLA_ENABLED_ENGINES", "AUDIOLLA_PRELOAD"):
        monkeypatch.delenv(var, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    sys.modules.pop("audiolla.config", None)
    return importlib.import_module("audiolla.config")


@pytest.fixture
def fake_registry(tmp_path: Path) -> Path:
    p = tmp_path / "engines.json"
    p.write_text(json.dumps({
        "engines": {
            "htdemucs": {
                "executor": "demucs",
                "variant": "htdemucs",
                "stems": ["drums", "bass", "other", "vocals"],
            },
            "matchering": {
                "executor": "matchering",
            },
            "librosa-analyze": {
                "executor": "librosa_analyze",
            },
        }
    }))
    return p


# ── ENABLED_ENGINES env parsing ──────────────────────────────────────────────

def test_enabled_engines_empty_means_all(monkeypatch, fake_registry):
    cfg = _reload_config(monkeypatch, fake_registry)
    assert cfg.ENABLED_ENGINES == []
    reg = cfg.load_registry()
    assert set(reg) == {"htdemucs", "matchering", "librosa-analyze"}


def test_enabled_engines_filters_registry(monkeypatch, fake_registry):
    cfg = _reload_config(
        monkeypatch, fake_registry,
        AUDIOLLA_ENABLED_ENGINES="htdemucs,matchering",
    )
    assert cfg.ENABLED_ENGINES == ["htdemucs", "matchering"]
    reg = cfg.load_registry()
    assert set(reg) == {"htdemucs", "matchering"}
    assert "librosa-analyze" not in reg


def test_enabled_engines_preserves_order(monkeypatch, fake_registry):
    cfg = _reload_config(
        monkeypatch, fake_registry,
        AUDIOLLA_ENABLED_ENGINES="matchering,htdemucs",
    )
    reg = cfg.load_registry()
    assert list(reg) == ["matchering", "htdemucs"]


def test_enabled_engines_trims_whitespace(monkeypatch, fake_registry):
    cfg = _reload_config(
        monkeypatch, fake_registry,
        AUDIOLLA_ENABLED_ENGINES=" htdemucs , , matchering ,",
    )
    assert cfg.ENABLED_ENGINES == ["htdemucs", "matchering"]


def test_enabled_engines_unknown_slug_fails(monkeypatch, fake_registry):
    cfg = _reload_config(
        monkeypatch, fake_registry,
        AUDIOLLA_ENABLED_ENGINES="htdemucs,does-not-exist",
    )
    with pytest.raises(ValueError, match="does-not-exist"):
        cfg.load_registry()


# ── load_registry schema validation ──────────────────────────────────────────

def test_load_registry_missing_file_raises(monkeypatch, tmp_path):
    missing = tmp_path / "no-such-file.json"
    cfg = _reload_config(monkeypatch, missing)
    with pytest.raises(FileNotFoundError):
        cfg.load_registry()


def test_load_registry_bad_top_level_raises(monkeypatch, tmp_path):
    p = tmp_path / "engines.json"
    p.write_text(json.dumps(["not", "an", "object"]))
    cfg = _reload_config(monkeypatch, p)
    with pytest.raises(ValueError, match="top-level"):
        cfg.load_registry()


def test_load_registry_unknown_executor_raises(monkeypatch, tmp_path):
    p = tmp_path / "engines.json"
    p.write_text(json.dumps({
        "engines": {"x": {"executor": "telepathy"}}
    }))
    cfg = _reload_config(monkeypatch, p)
    with pytest.raises(ValueError, match="telepathy"):
        cfg.load_registry()


def test_load_registry_empty_engines_raises(monkeypatch, tmp_path):
    p = tmp_path / "engines.json"
    p.write_text(json.dumps({"engines": {}}))
    cfg = _reload_config(monkeypatch, p)
    with pytest.raises(ValueError, match="non-empty"):
        cfg.load_registry()


# ── duration parser ───────────────────────────────────────────────────────────

def test_duration_env_accepts_bare_seconds(monkeypatch, fake_registry):
    cfg = _reload_config(monkeypatch, fake_registry, AUDIOLLA_ENGINE_TTL="300")
    assert cfg.ENGINE_IDLE_TIMEOUT_SECONDS == 300.0


def test_duration_env_accepts_go_style(monkeypatch, fake_registry):
    cfg = _reload_config(monkeypatch, fake_registry, AUDIOLLA_ENGINE_TTL="1h30m5s")
    assert cfg.ENGINE_IDLE_TIMEOUT_SECONDS == 3600 + 30 * 60 + 5


def test_duration_env_rejects_garbage(monkeypatch, fake_registry):
    monkeypatch.setenv("AUDIOLLA_ENGINES_FILE", str(fake_registry))
    monkeypatch.setenv("AUDIOLLA_ENGINE_TTL", "yesterday")
    sys.modules.pop("audiolla.config", None)
    with pytest.raises(ValueError, match="AUDIOLLA_ENGINE_TTL"):
        importlib.import_module("audiolla.config")


def test_device_rejects_garbage(monkeypatch, fake_registry):
    monkeypatch.setenv("AUDIOLLA_ENGINES_FILE", str(fake_registry))
    monkeypatch.setenv("AUDIOLLA_DEVICE", "potato")
    sys.modules.pop("audiolla.config", None)
    with pytest.raises(ValueError, match="AUDIOLLA_DEVICE"):
        importlib.import_module("audiolla.config")


def test_device_accepts_cuda_n(monkeypatch, fake_registry):
    cfg = _reload_config(monkeypatch, fake_registry, AUDIOLLA_DEVICE="cuda:1")
    assert cfg.DEVICE == "cuda:1"
