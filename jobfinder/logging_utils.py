# file: jobfinder/logging_utils.py
from __future__ import annotations

import logging
import os
import sys


def setup_logging(default_level: str | None = None) -> None:
    """
    Console logging. Controlled by env LOG_LEVEL (DEBUG/INFO/WARN/ERROR).
    Why: make import failures and provider resolution visible.
    """
    level_name = (os.getenv("LOG_LEVEL") or default_level or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    root = logging.getLogger()
    # Avoid duplicate handlers on reload
    if not root.handlers:
        h = logging.StreamHandler(stream=sys.stdout)
        fmt = logging.Formatter(
            fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            datefmt="%H:%M:%S",
        )
        h.setFormatter(fmt)
        root.addHandler(h)
    root.setLevel(level)
