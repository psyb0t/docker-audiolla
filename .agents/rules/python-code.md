# Python code rules

Prefix: PY.

`make lint` (`flake8 src`, then `mypy src`) and `make format` (`isort src`, then `black src`) run in the dev container. CI runs `make lint`, `make test` and the `make generate` drift check on every push.

## Style and typing

- **PY1:** Start every module in `src/audiolla/` with `from __future__ import annotations`, except `__init__.py` and `server.py`. `server.py` must not have it: PEP 563 string annotations turned the generated request models into `ForwardRef`s and broke FastAPI's body detection in v1.0.0 (the note at the top of `server.py`).
- **PY2:** flake8 allows 99 columns and ignores `E203` and `W503` (`.flake8`, which also excludes `schema/_generated.py`). mypy runs with `ignore_missing_imports` and overrides for the ML libraries the dev image lacks (`pyproject.toml`).

## Configuration

- **PY4:** Read environment variables in `src/audiolla/config.py`, once, at import, into typed module constants (`AUDIOLLA_ENGINE_TTL` becomes `ENGINE_IDLE_TIMEOUT_SECONDS`). Other modules import `config` and read the constant. Existing exceptions: `LOG_LEVEL` in `logging.py` and `engines/uvr_separator.py`, `AUDIOLLA_ENABLE_NONCOMMERCIAL` in `engines/music_gen.py`, `HUGGINGFACE_TOKEN` in `engines/diarize_pyannote_engine.py`. Do not add more.
- **PY5:** New settings use the `AUDIOLLA_` prefix and the existing parsers: `_int_env`, `_float_env`, `_list_env` (comma-separated, trimmed, empties dropped), `_duration_env` (seconds or Go-style `3h30m5s`), `_bool_env` (`1/0`, `true/false`, `yes/no`, `on/off`, empty means the default).
- **PY6:** A bad value stops startup with a `ValueError` naming the variable and what it accepts (`AUDIOLLA_DEVICE`, `AUDIOLLA_FETCH_MODE`, `AUDIOLLA_SWEEPER_INTERVAL`). Never fall back to the default on a bad value. A setting that is parsed must also be used; `AUDIOLLA_LOAD_TIMEOUT` and `AUDIOLLA_JOB_MAX_CONCURRENT` currently are not.

## Engines versus functions

- **PY7:** Stateful or heavy work with a lifecycle (loads weights, caches a resource, needs a lock) is an engine: a subclass of `EngineBase` in `src/audiolla/engines/` with a slug in the registries. Stateless, cheap DSP is a plain function in `src/audiolla/audio.py`, called from handlers and MCP tools, with no slug (the rule of thumb in the `engines/__init__.py` docstring).

## Errors

- **PY10:** An engine or `audio.py` failure the caller caused raises `AudioConversionError` or a subclass (`UVRSeparatorError`, `MusicGenError`, `DiarizeError`, ...) with a message the caller can act on; handlers map it to 400 and MCP tools to `ValueError`. Path problems raise `FilePathError`, URL problems `FetchError`, both mapped to 400.
- **PY12:** Broad `except Exception` around an optional step (the sweepers, preload, `unload_all`) logs with `log.exception` and carries `# noqa: BLE001`.

## Logging

- **PY13:** `src/audiolla/logging.py` owns the handlers: `configure()` installs one JSON formatter on stderr for the root and uvicorn loggers, called once from `__main__.py`. Do not add handlers, call `logging.basicConfig` or `print()` in `src/` (the one `print` is `logging.py`'s own warning before logging exists).
- **PY14:** Name loggers explicitly under `audiolla.`: `logging.getLogger("audiolla.<module>")` per module (`audiolla.server`, `audiolla.fetch`, `audiolla.mcp`), `audiolla.engine.<slug>` per engine (`EngineBase.__init__`), `audiolla.request` for the request summary. Structured fields in `extra={...}` are promoted by the formatter to top-level JSON keys.
