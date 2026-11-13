"""Strict JSON-to-Decimal conversion shared by adapters. Rejects bool, NaN, Infinity, None."""

from __future__ import annotations

import math
from decimal import Decimal, InvalidOperation
from typing import Any

from bangzen_prime.errors import ExternalServiceError


class MalformedData(ExternalServiceError):
    def __init__(self, service: str, detail: str) -> None:
        super().__init__(f"{service} returned malformed data: {detail}", service=service,
                         retryable=False)


def to_decimal(value: Any, *, service: str, field: str) -> Decimal:
    if value is None or isinstance(value, bool):
        raise MalformedData(service, f"{field} missing or boolean")
    if isinstance(value, float):
        if not math.isfinite(value):
            raise MalformedData(service, f"{field} is not finite")
        return Decimal(repr(value))
    if isinstance(value, (int, str)):
        try:
            result = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise MalformedData(service, f"{field} is not numeric") from None
        if not result.is_finite():
            raise MalformedData(service, f"{field} is not finite")
        return result
    raise MalformedData(service, f"{field} has unexpected type")


def require_str(value: Any, *, service: str, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise MalformedData(service, f"{field} missing")
    return value.strip()
