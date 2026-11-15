"""Deterministic fingerprint for frozen research configurations.

Used to pin the configuration that a walk-forward run or a forward paper test used, so
that any later change is detectable. Floats are rejected because their text form is not a
stable contract. Decimals are normalised, so 0.001 and 0.0010 hash the same.
"""

from __future__ import annotations

import dataclasses
import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from bangzen_prime.core.errors import DomainError


def _normalize(value: Any) -> Any:
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _normalize(getattr(value, field.name))
            for field in dataclasses.fields(value)
        }
    if isinstance(value, bool) or value is None or isinstance(value, str):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise DomainError("non-finite Decimal cannot be frozen")
        return format(value.normalize(), "f")
    if isinstance(value, datetime):
        if value.tzinfo is None or value.utcoffset() is None:
            raise DomainError("datetime must be timezone-aware to be frozen")
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _normalize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_normalize(v) for v in value]
    if isinstance(value, float):
        raise DomainError("floats are not allowed in frozen configuration; use Decimal")
    raise DomainError(f"unsupported type for frozen configuration: {type(value).__name__}")


def canonical_json(value: Any) -> str:
    return json.dumps(
        _normalize(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True
    )


def config_hash(value: Any) -> str:
    """SHA-256 hex digest of the canonical JSON form of ``value``."""
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()
