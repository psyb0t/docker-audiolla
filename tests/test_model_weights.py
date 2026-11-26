from __future__ import annotations

import sys
from types import ModuleType

from audiolla.engines import _weights


def test_enabled_download_modes_try_local_hf_files_first(monkeypatch):
    hub_errors = ModuleType("huggingface_hub.errors")
    monkeypatch.setattr(hub_errors, "LocalEntryNotFoundError", FileNotFoundError, raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub.errors", hub_errors)
    monkeypatch.setattr(_weights.config, "MODEL_DOWNLOAD", "on-demand")
    calls = []

    def loader(model, **options):
        calls.append((model, options))
        return "weights"

    assert _weights.load_pretrained(loader, "model") == "weights"
    assert calls == [("model", {"local_files_only": True})]


def test_cache_miss_falls_back_to_download(monkeypatch):
    hub_errors = ModuleType("huggingface_hub.errors")
    monkeypatch.setattr(hub_errors, "LocalEntryNotFoundError", FileNotFoundError, raising=False)
    monkeypatch.setitem(sys.modules, "huggingface_hub.errors", hub_errors)
    monkeypatch.setattr(_weights.config, "MODEL_DOWNLOAD", "startup")
    calls = []

    def loader(model, **options):
        calls.append((model, options))
        if options.get("local_files_only"):
            raise OSError("cache miss")
        return "weights"

    assert _weights.load_pretrained(loader, "model") == "weights"
    assert calls == [("model", {"local_files_only": True}), ("model", {})]
