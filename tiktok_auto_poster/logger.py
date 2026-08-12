"""Thin logging wrapper used across the pipeline."""
from __future__ import annotations

import logging
import sys
from pathlib import Path

from .config import CONFIG

_LOGGER_NAME = "tiktok_auto_poster"


def _setup() -> logging.Logger:
    CONFIG.ensure_dirs()
    log = logging.getLogger(_LOGGER_NAME)
    if log.handlers:
        return log  # already configured

    log.setLevel(logging.DEBUG)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    log.addHandler(ch)

    # File
    fh = logging.FileHandler(CONFIG.logs_dir / "auto_poster.log", encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)
    log.addHandler(fh)

    return log


logger = _setup()
