"""Structured logging setup."""

from __future__ import annotations

import logging


def configure() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )
