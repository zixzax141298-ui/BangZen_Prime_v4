"""Size-based log rotation for the file logger (stdlib only, works on Termux and VPS).

Keeps the same redaction and JSON format as the stream logger. Old files are renamed by
RotatingFileHandler, so at most ``backup_count + 1`` files exist.
"""

from __future__ import annotations

import logging
import logging.handlers
import os

from bangzen_prime.core.logging_utils import JsonFormatter, RedactionFilter

DEFAULT_MAX_BYTES = 5 * 1024 * 1024
DEFAULT_BACKUP_COUNT = 5


def configure_file_logging(
    path: str | os.PathLike[str],
    level: str = "INFO",
    max_bytes: int = DEFAULT_MAX_BYTES,
    backup_count: int = DEFAULT_BACKUP_COUNT,
) -> logging.Logger:
    if max_bytes < 1024:
        raise ValueError("max_bytes must be at least 1024")
    if backup_count < 0:
        raise ValueError("backup_count must not be negative")
    logger = logging.getLogger("bangzen_prime")
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.handlers.RotatingFileHandler(
        os.fspath(path), maxBytes=max_bytes, backupCount=backup_count, encoding="utf-8"
    )
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
