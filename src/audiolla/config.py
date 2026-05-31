"""Env-driven config — parsed at import time, fail-fast on bad input."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    if raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name}={raw!r} is not an integer") from exc


def _float_env(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name}={raw!r} is not a number") from exc


def _list_env(name: str) -> list[str]:
    raw = os.environ.get(name, "")
    return [s.strip() for s in raw.split(",") if s.strip()]


_DURATION_RE = re.compile(
    r"^\s*(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?\s*(?:(\d+(?:\.\d+)?)\s*s)?\s*$",
    re.IGNORECASE,
)


def _duration_env(name: str, default: float) -> float:
    """Parse a duration env var.

    Accepts a bare number (seconds) or Go-style strings like "3h30m5s",
    "45m", "90s". Returns total seconds.
    """
    raw = os.environ.get(name, "").strip()
    if raw == "":
        return default
    try:
        return float(raw)
    except ValueError:
        pass
    match = _DURATION_RE.match(raw)
    if not match or not any(match.groups()):
        raise ValueError(
            f"{name}={raw!r} must be seconds (e.g. 600) or Go-style "
            "duration like '3h30m5s', '45m', '90s'"
        )
    hours = int(match.group(1) or 0)
    minutes = int(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    return hours * 3600 + minutes * 60 + seconds


# Optional bearer token gating every HTTP route.
# Empty/unset = wide open. /healthz stays unauthenticated so k8s probes work.
AUTH_TOKEN: str = os.environ.get("AUDIOLLA_AUTH_TOKEN", "").strip()

DEVICE: str = os.environ.get("AUDIOLLA_DEVICE", "auto").strip() or "auto"
if DEVICE not in ("auto", "cpu", "cuda") and not DEVICE.startswith("cuda:"):
    raise ValueError(
        f"AUDIOLLA_DEVICE={DEVICE!r} must be 'auto', 'cpu', 'cuda', or 'cuda:N'"
    )

ENGINES_FILE: Path = Path(
    os.environ.get("AUDIOLLA_ENGINES_FILE", "/app/engines.json")
).resolve()

DATA_DIR: Path = Path(
    os.environ.get("AUDIOLLA_DATA_DIR", "/data")
).resolve()

# Flat per-engine snapshot directory: engines with weights get
# DATA_DIR / models / <slug> / ... populated by entrypoint.sh.
MODELS_DIR: Path = DATA_DIR / "models"

# Server-side file staging area for the /v1/files API.
FILES_DIR: Path = DATA_DIR / "files"

ENGINE_IDLE_TIMEOUT_SECONDS: float = _duration_env("AUDIOLLA_ENGINE_TTL", 600.0)
SWEEPER_INTERVAL_SECONDS: float = _duration_env("AUDIOLLA_SWEEPER_INTERVAL", 60.0)
LOAD_TIMEOUT_SECONDS: float = _duration_env("AUDIOLLA_LOAD_TIMEOUT", 300.0)

MAX_UPLOAD_BYTES: int = _int_env("AUDIOLLA_MAX_UPLOAD_BYTES", 200 * 1024 * 1024)

PRELOAD: list[str] = _list_env("AUDIOLLA_PRELOAD")
ENABLED_ENGINES: list[str] = _list_env("AUDIOLLA_ENABLED_ENGINES")


# ── URL fetch policy ─────────────────────────────────────────────────────────
# Controls server-side fetching for `file_url` and PUT-to-`output_url` flows.
# Default `disabled` keeps the server a pure local-processing box: any caller
# passing file_url / output_url gets a 400. Switch to allowlist (preferred)
# or denylist (caveat emptor — leaky by design) to opt in.

def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw == "":
        return default
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    raise ValueError(f"{name}={raw!r} must be a boolean (1/0, true/false, yes/no, on/off)")


FETCH_MODE: str = (
    os.environ.get("AUDIOLLA_FETCH_MODE", "disabled").strip().lower()
    or "disabled"
)
if FETCH_MODE not in ("disabled", "allowlist", "denylist"):
    raise ValueError(
        f"AUDIOLLA_FETCH_MODE={FETCH_MODE!r} must be 'disabled', "
        "'allowlist', or 'denylist'"
    )

FETCH_HOSTS: list[str] = _list_env("AUDIOLLA_FETCH_HOSTS")
if FETCH_MODE == "allowlist" and not FETCH_HOSTS:
    raise ValueError(
        "AUDIOLLA_FETCH_MODE=allowlist requires AUDIOLLA_FETCH_HOSTS "
        "to be a non-empty comma-separated list"
    )

FETCH_SCHEMES: list[str] = [
    s.lower() for s in (_list_env("AUDIOLLA_FETCH_SCHEMES") or ["https"])
]
for _s in FETCH_SCHEMES:
    if _s not in ("http", "https"):
        raise ValueError(
            f"AUDIOLLA_FETCH_SCHEMES contains unsupported scheme {_s!r}; "
            "supported: http, https"
        )

FETCH_TIMEOUT_SECONDS: float = _duration_env("AUDIOLLA_FETCH_TIMEOUT", 30.0)
FETCH_ALLOW_PRIVATE: bool = _bool_env("AUDIOLLA_FETCH_ALLOW_PRIVATE", False)
FETCH_MAX_REDIRECTS: int = _int_env("AUDIOLLA_FETCH_MAX_REDIRECTS", 5)

_VALID_EXECUTORS = frozenset({
    "demucs",
    "matchering",
    "pedalboard_chain",
    "librosa_analyze",
    "sox_transform",
})


def load_registry() -> dict[str, dict]:
    """Read engines.json and return {slug: entry}."""
    if not ENGINES_FILE.exists():
        raise FileNotFoundError(f"engines.json not found at {ENGINES_FILE}")
    with ENGINES_FILE.open("r", encoding="utf-8") as fh:
        raw = json.load(fh)
    if not isinstance(raw, dict) or "engines" not in raw:
        raise ValueError(f"{ENGINES_FILE}: expected top-level object with 'engines' key")
    engines = raw["engines"]
    if not isinstance(engines, dict) or not engines:
        raise ValueError(f"{ENGINES_FILE}: 'engines' must be a non-empty object")
    for slug, entry in engines.items():
        if not isinstance(entry, dict):
            raise ValueError(f"{ENGINES_FILE}: engine {slug!r} entry must be an object")
        executor = entry.get("executor")
        if executor not in _VALID_EXECUTORS:
            raise ValueError(
                f"{ENGINES_FILE}: engine {slug!r} executor={executor!r} must be one of "
                f"{sorted(_VALID_EXECUTORS)}"
            )
    if ENABLED_ENGINES:
        missing = [s for s in ENABLED_ENGINES if s not in engines]
        if missing:
            raise ValueError(
                f"AUDIOLLA_ENABLED_ENGINES references unknown slug(s) {missing}; "
                f"available in {ENGINES_FILE}: {sorted(engines)}"
            )
        engines = {s: engines[s] for s in ENABLED_ENGINES}
    return engines
