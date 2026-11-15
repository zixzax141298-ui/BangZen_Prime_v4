"""Price indicators with explicit, documented edge-case behaviour. Inputs are Decimal."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from bangzen_prime.core.errors import DomainError

ZERO = Decimal(0)
HUNDRED = Decimal(100)


def _require(values: Sequence[Decimal], minimum: int, name: str) -> None:
    if len(values) < minimum:
        raise DomainError(f"{name} needs at least {minimum} values, got {len(values)}")


def sma(values: Sequence[Decimal], period: int) -> Decimal:
    if period < 1:
        raise DomainError("period must be >= 1")
    _require(values, period, "sma")
    window = values[-period:]
    return sum(window, ZERO) / Decimal(period)


def ema(values: Sequence[Decimal], period: int) -> Decimal:
    """Seeded with the SMA of the first `period` values, then standard alpha = 2/(n+1)."""
    if period < 1:
        raise DomainError("period must be >= 1")
    _require(values, period, "ema")
    alpha = Decimal(2) / Decimal(period + 1)
    value = sum(values[:period], ZERO) / Decimal(period)
    for price in values[period:]:
        value = alpha * price + (1 - alpha) * value
    return value


def rsi(values: Sequence[Decimal], period: int = 14) -> Decimal:
    """Wilder RSI on closes.

    Edge cases: no losses and gains -> 50 (flat series is neutral by definition);
    no losses with gains -> 100; no gains with losses -> 0.
    """
    if period < 1:
        raise DomainError("period must be >= 1")
    _require(values, period + 1, "rsi")
    changes = [values[i] - values[i - 1] for i in range(1, len(values))]
    gains = [c if c > 0 else ZERO for c in changes[:period]]
    losses = [-c if c < 0 else ZERO for c in changes[:period]]
    avg_gain = sum(gains, ZERO) / Decimal(period)
    avg_loss = sum(losses, ZERO) / Decimal(period)
    for change in changes[period:]:
        gain = change if change > 0 else ZERO
        loss = -change if change < 0 else ZERO
        avg_gain = (avg_gain * (period - 1) + gain) / Decimal(period)
        avg_loss = (avg_loss * (period - 1) + loss) / Decimal(period)
    if avg_gain == 0 and avg_loss == 0:
        return Decimal(50)
    if avg_loss == 0:
        return HUNDRED
    if avg_gain == 0:
        return ZERO
    rs = avg_gain / avg_loss
    return HUNDRED - HUNDRED / (1 + rs)


def mean_abs_change(values: Sequence[Decimal], period: int) -> Decimal:
    """Close-only volatility proxy (not a true ATR, which needs high/low data)."""
    if period < 1:
        raise DomainError("period must be >= 1")
    _require(values, period + 1, "mean_abs_change")
    window = values[-(period + 1) :]
    diffs = [abs(window[i] - window[i - 1]) for i in range(1, len(window))]
    return sum(diffs, ZERO) / Decimal(period)


def zscore(values: Sequence[Decimal]) -> Decimal:
    """Z-score of the last value against the population mean and stdev of all values.

    A zero-variance series returns 0 instead of dividing by zero.
    """
    _require(values, 2, "zscore")
    n = Decimal(len(values))
    mean = sum(values, ZERO) / n
    variance = sum(((v - mean) ** 2 for v in values), ZERO) / n
    if variance == 0:
        return ZERO
    return (values[-1] - mean) / variance.sqrt()
