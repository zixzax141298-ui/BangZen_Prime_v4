"""Validated value parsing. Money and prices are Decimal; floats are rejected."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from bangzen_prime.errors import DomainError


def parse_decimal(value: Any, name: str) -> Decimal:
    if isinstance(value, bool) or isinstance(value, float):
        raise DomainError(f"{name} must be a str, int or Decimal, not {type(value).__name__}")
    if isinstance(value, Decimal):
        result = value
    elif isinstance(value, (int, str)):
        try:
            result = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise DomainError(f"{name} is not a number") from None
    else:
        raise DomainError(f"{name} has unsupported type {type(value).__name__}")
    if not result.is_finite():
        raise DomainError(f"{name} must be finite")
    return result


def positive(value: Any, name: str) -> Decimal:
    result = parse_decimal(value, name)
    if result <= 0:
        raise DomainError(f"{name} must be greater than zero")
    return result


def non_negative(value: Any, name: str) -> Decimal:
    result = parse_decimal(value, name)
    if result < 0:
        raise DomainError(f"{name} must not be negative")
    return result


def percent(value: Any, name: str, *, allow_zero: bool = True) -> Decimal:
    result = parse_decimal(value, name)
    low_ok = result >= 0 if allow_zero else result > 0
    if not (low_ok and result <= 100):
        raise DomainError(f"{name} must be within the percentage range")
    return result


def unit_interval(value: Any, name: str) -> Decimal:
    result = parse_decimal(value, name)
    if not (Decimal("0") <= result <= Decimal("1")):
        raise DomainError(f"{name} must be within [0, 1]")
    return result
