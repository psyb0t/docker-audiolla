"""uvicorn entrypoint — `python -m audiolla`."""

from __future__ import annotations


def main() -> int:
    from .logging import configure as configure_logging

    configure_logging()

    import logging
    import uvicorn

    log = logging.getLogger("audiolla")
    log.info("audiolla: starting on 0.0.0.0:8000")
    uvicorn.run("audiolla.server:app", host="0.0.0.0", port=8000, log_config=None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
