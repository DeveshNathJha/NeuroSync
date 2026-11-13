"""
src/utils/logger.py
-------------------
One shared application logger. Log files live in <data_dir>/logs (outside
the repository) and rotate at 2 MB x 3 files. Never log names, free-text
notes or raw sensor data – only ids, counts and technical messages.

Usage:
    from src.utils.logger import logger
    logger.info("session started")
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def get_logger(name: str = "neurosync") -> logging.Logger:
    """Return the shared logger, configuring its handlers once."""
    log = logging.getLogger(name)
    if log.handlers:
        return log
    log.setLevel(logging.INFO)
    log.propagate = False
    fmt = logging.Formatter(_FORMAT)

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    log.addHandler(console)

    try:  # file logging is best effort (e.g. read-only environments)
        from src.config import data_dir

        log_dir = data_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(log_dir / "neurosync.log", maxBytes=2 * 1024 * 1024,
                                           backupCount=3, encoding="utf-8")
        file_handler.setFormatter(fmt)
        log.addHandler(file_handler)
    except OSError as exc:
        log.warning(f"File logging disabled: {exc}")
    return log


logger = get_logger()
