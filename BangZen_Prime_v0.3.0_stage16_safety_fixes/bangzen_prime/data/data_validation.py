"""Validation of market numbers before they reach the AI brain or a signal.

Every calculation uses Decimal. Floats are rejected at the boundary, because a float rounding
error can flip a comparison near a threshold.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from bangzen_prime.core.errors import DomainError

HUNDRED = Decimal(100)


def _finite_positive(value: object) -> bool:
    return isinstance(value, Decimal) and value.is_finite() and value > 0


def price_deviation_pct(a: object, b: object) -> Decimal | None:
    """Relative difference between two prices, in percent of the smaller one. None if invalid."""
    if not (_finite_positive(a) and _finite_positive(b)):
        return None
    lo, hi = (a, b) if a <= b else (b, a)
    try:
        return (hi - lo) / lo * HUNDRED
    except (InvalidOperation, ZeroDivisionError):
        return None


def prices_agree(a: object, b: object, max_deviation_pct: Decimal) -> bool:
    """True only when both prices are valid and within the allowed deviation (inclusive)."""
    if (
        not isinstance(max_deviation_pct, Decimal)
        or not max_deviation_pct.is_finite()
        or max_deviation_pct < 0
    ):
        return False
    deviation = price_deviation_pct(a, b)
    return deviation is not None and deviation <= max_deviation_pct


def is_fresh(
    observed_at_epoch: object, now_epoch: object, max_age_seconds: int
) -> bool:
    """Reject observations that are older than the limit, in the future, or non-numeric."""
    if (
        isinstance(max_age_seconds, bool)
        or not isinstance(max_age_seconds, int)
        or max_age_seconds <= 0
    ):
        return False
    if not isinstance(observed_at_epoch, Decimal) or not isinstance(now_epoch, Decimal):
        return False
    if not (observed_at_epoch.is_finite() and now_epoch.is_finite()):
        return False
    age = now_epoch - observed_at_epoch
    return Decimal(0) <= age <= Decimal(max_age_seconds)


def validate_holder_profile(profile: object, mint: str) -> None:
    """Fail closed: raise DomainError unless the holder profile is complete and for this mint.

    Missing, malformed, or mismatched holder evidence must never pass a safety gate.
    """
    if profile is None:
        raise DomainError("holder profile missing")
    if getattr(profile, "mint", None) != mint:
        raise DomainError("holder profile is for a different mint")
    count = getattr(profile, "holder_count", None)
    if isinstance(count, bool) or not isinstance(count, int) or count < 0:
        raise DomainError("holder_count must be a non-negative integer")
    share = getattr(profile, "top_holder_share_pct", None)
    if share is not None and (
        not isinstance(share, Decimal)
        or not share.is_finite()
        or not (Decimal(0) <= share <= HUNDRED)
    ):
        raise DomainError(
            "top_holder_share_pct must be None or a Decimal within [0, 100]"
        )
    source = getattr(profile, "source", None)
    if not isinstance(source, str) or not source.strip():
        raise DomainError("holder profile source is required")
