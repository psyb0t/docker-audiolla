"""Pytest config — ensure src/ is on sys.path when running outside the dev image."""

from __future__ import annotations

import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_SRC = _ROOT / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

# Point config.ENGINES_FILE at the real file so server.py can be imported
# in tests that mock ENGINES/REGISTRY after import.
_engines_json = _ROOT / "engines.json"
if _engines_json.exists():
    os.environ.setdefault("AUDIOLLA_ENGINES_FILE", str(_engines_json))
