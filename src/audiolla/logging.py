"""Centralised logging setup — JSON output, single init path, request correlation.

Every audiolla process funnels logs through this module. ``configure()`` is
called exactly once from ``audiolla.__main__`` before uvicorn starts; every
logger in the application (and uvicorn's own ``uvicorn`` / ``uvicorn.error``
/ ``uvicorn.access`` loggers) emits through the same JSON formatter so a
log aggregator sees one consistent shape regardless of where a line
originates.

Each log line is a single JSON object — line-delimited JSON / NDJSON
friendly. Every record carries:

    {
      "ts":         "2026-06-08T22:53:19.799Z",   ISO-8601 UTC
      "level":      "INFO",
      "logger":     "audiolla.server",
      "file":       "server.py",
      "line":       213,
      "func":       "list_engines",
      "msg":        "<rendered message>",

      // process / runtime identity (constant for the process lifetime)
      "service":    "audiolla",
      "version":    "<package version>",
      "pid":        12345,
      "host":       "<container hostname>",
      "thread":     "<thread name>",

      // request-scoped context (populated by the request middleware)
      "request_id": "abcd1234...",                 set per HTTP request
      "method":     "POST",
      "path":       "/v1/audio/normalize",

      // optional, only when relevant
      "exc":        "<traceback string>",          if exc_info is set
      "stack":      "<stack trace>"                if stack_info is set
    }

Plus anything the caller passed via ``extra={...}`` — domain-specific
context (engine slug, job id, file path, duration_ms, etc.) — surfaces
as a top-level key in the JSON.

Driven by ``LOG_LEVEL`` (DEBUG | INFO | WARNING | ERROR | CRITICAL,
case-insensitive; ``WARN`` accepted as alias; defaults to ``INFO``).
"""

from __future__ import annotations

import contextvars
import datetime as _dt
import json
import logging
import os
import socket
import sys
import uuid

_DATEFMT_ISO = "%Y-%m-%dT%H:%M:%S"


# Process-lifetime constants captured once at import.
_PID = os.getpid()
_HOST = socket.gethostname()


def _package_version() -> str:
    try:
        from importlib.metadata import version as _v  # noqa: PLC0415
        return _v("audiolla")
    except Exception:  # noqa: BLE001
        return "unknown"


_VERSION = _package_version()


# Request-scoped context. The request-logging middleware populates these
# at the start of each HTTP request and resets them at the end; any log
# emitted between those points carries the correlation fields
# automatically, no `extra={}` plumbing required.
request_id_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "audiolla_request_id", default=None,
)
request_method_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "audiolla_request_method", default=None,
)
request_path_ctx: contextvars.ContextVar[str | None] = contextvars.ContextVar(
    "audiolla_request_path", default=None,
)


def new_request_id() -> str:
    """Generate an ID for the X-Request-Id header.

    32-char hex (uuid4 without dashes) — short enough to grep, long
    enough to be collision-free across realistic traffic volumes.
    """
    return uuid.uuid4().hex


class JsonFormatter(logging.Formatter):
    """Render each LogRecord as a single-line JSON object.

    Standard % / {} / $ interpolation is honoured via
    ``record.getMessage()``. Exception tracebacks fold into the JSON
    under ``exc`` rather than printed as a separate stanza so each log
    line stays a single JSON value.
    """

    def format(self, record: logging.LogRecord) -> str:
        ts = _dt.datetime.fromtimestamp(
            record.created, tz=_dt.timezone.utc,
        ).strftime(_DATEFMT_ISO) + f".{int(record.msecs):03d}Z"

        payload: dict[str, object] = {
            "ts": ts,
            "level": record.levelname,
            "logger": record.name,
            "file": record.filename,
            "line": record.lineno,
            "func": record.funcName,
            "msg": record.getMessage(),
            "service": "audiolla",
            "version": _VERSION,
            "pid": _PID,
            "host": _HOST,
            "thread": record.threadName,
        }

        # Request-scoped correlation. Empty fields are dropped to keep
        # non-HTTP logs (startup, background jobs, prefetch) tidy.
        rid = request_id_ctx.get()
        if rid:
            payload["request_id"] = rid
        method = request_method_ctx.get()
        if method:
            payload["method"] = method
        path = request_path_ctx.get()
        if path:
            payload["path"] = path

        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        if record.stack_info:
            payload["stack"] = self.formatStack(record.stack_info)

        # Surface any structured `extra={...}` fields the caller passed,
        # skipping the stdlib's own attributes so we don't double-record.
        for key, value in record.__dict__.items():
            if key in _STD_RECORD_ATTRS or key in payload:
                continue
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                value = repr(value)
            payload[key] = value

        return json.dumps(payload, ensure_ascii=False, default=str)


# stdlib's LogRecord attribute names — anything not here that ends up on
# the record came from the caller's `extra=` kwarg and should surface in
# the JSON output.
_STD_RECORD_ATTRS: frozenset[str] = frozenset({
    "args", "asctime", "created", "exc_info", "exc_text", "filename",
    "funcName", "levelname", "levelno", "lineno", "message", "module",
    "msecs", "msg", "name", "pathname", "process", "processName",
    "relativeCreated", "stack_info", "thread", "threadName", "taskName",
})


def _resolve_level(raw: str | None) -> int:
    if not raw:
        return logging.INFO
    key = raw.strip().upper()
    if key == "WARN":
        key = "WARNING"
    mapping = logging.getLevelNamesMapping()  # Python 3.11+
    if key in mapping:
        return mapping[key]
    print(
        f"[audiolla.logging] WARN: LOG_LEVEL={raw!r} not recognised; "
        f"falling back to INFO",
        file=sys.stderr,
    )
    return logging.INFO


_configured = False


def configure() -> None:
    """Install the JSON formatter on the root logger + uvicorn loggers.

    Idempotent — safe to call more than once; subsequent calls are no-ops.
    """
    global _configured
    if _configured:
        return

    level = _resolve_level(os.environ.get("LOG_LEVEL"))

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())

    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    # Uvicorn's loggers default to propagate=False, so the root handler
    # alone wouldn't catch them. Wire each one explicitly.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers.clear()
        lg.addHandler(handler)
        lg.setLevel(level)
        lg.propagate = False

    # Quiet noisy third-party loggers at DEBUG (TLS handshakes / connection
    # pool chatter would otherwise flood the output). Operators can
    # re-enable per-logger if they need that detail.
    for noisy in ("urllib3", "httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(max(level, logging.INFO))

    _configured = True
    logging.getLogger("audiolla").debug(
        "logging configured: level=%s format=json version=%s pid=%d host=%s",
        logging.getLevelName(level), _VERSION, _PID, _HOST,
    )
