"""Structured JSON logging with secret redaction."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import TextIO

_TELEGRAM_TOKEN = re.compile(r"\b\d{6,12}:[A-Za-z0-9_-]{30,}\b")
_KEY_VALUE = re.compile(
    r"((?:token|secret|password|private[_-]?key|api[_-]?key)\s*[=:]\s*)([^\s,;&\"']+)",
    re.IGNORECASE,
)


def redact(text: str) -> str:
    """Remove secret-looking material from a log or error string."""
    text = _TELEGRAM_TOKEN.sub("<redacted-telegram-token>", text)
    return _KEY_VALUE.sub(lambda m: m.group(1) + "<redacted>", text)


class RedactionFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = redact(record.getMessage())
        record.args = ()
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        return json.dumps(payload, ensure_ascii=False)


def configure_logging(
    level: str = "INFO", stream: TextIO | None = None
) -> logging.Logger:
    logger = logging.getLogger("bangzen_prime")
    logger.setLevel(level)
    logger.handlers.clear()
    handler = logging.StreamHandler(stream or sys.stderr)
    handler.setFormatter(JsonFormatter())
    handler.addFilter(RedactionFilter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
