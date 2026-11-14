"""Risk arithmetic and portfolio snapshot. Units are explicit in every name."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bangzen_prime.domain.shared import ensure_utc
from bangzen_prime.domain.signals import PriceLevels
from bangzen_prime.domain.values import non_negative, percent, positive
from bangzen_prime.errors import DomainError


@dataclass(frozen=True)
class SizingResult:
    size_units: Decimal  # base token units
    risk_amount_quote: Decimal  # size * abs(entry - stop_loss), excludes fees
    estimated_fees_quote: Decimal
    exposure_quote: Decimal  # size * entry (notional)


def size_position(
    *, equity_quote: object, risk_pct: object, levels: PriceLevels, fee_rate: Decimal
) -> SizingResult:
    """Size so that (risk + round-trip fees) equals the per-trade risk budget."""
    equity = positive(equity_quote, "equity_quote")
    risk = percent(risk_pct, "risk_pct", allow_zero=False)
    fee = non_negative(fee_rate, "fee_rate")
    stop_distance = levels.risk_per_unit
    if stop_distance <= 0:
        raise DomainError("zero or negative stop distance")
    budget = equity * risk / Decimal(100)
    cost_per_unit = stop_distance + fee * (levels.entry + levels.stop_loss)
    size = budget / cost_per_unit
    return SizingResult(
        size_units=size,
        risk_amount_quote=size * stop_distance,
        estimated_fees_quote=fee * size * (levels.entry + levels.stop_loss),
        exposure_quote=size * levels.entry,
    )


@dataclass(frozen=True)
class OpenPosition:
    token_mint: str
    size_units: Decimal
    entry_price: Decimal

    @property
    def exposure_quote(self) -> Decimal:
        return self.size_units * self.entry_price


@dataclass(frozen=True)
class PortfolioSnapshot:
    equity_quote: Decimal
    peak_equity_quote: Decimal
    open_positions: tuple[OpenPosition, ...]
    as_of: datetime
    last_loss_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        equity_quote: object,
        peak_equity_quote: object,
        open_positions: tuple[OpenPosition, ...],
        as_of: datetime,
        last_loss_at: datetime | None = None,
    ) -> PortfolioSnapshot:
        equity = non_negative(equity_quote, "equity_quote")
        peak = positive(peak_equity_quote, "peak_equity_quote")
        if peak < equity:
            raise DomainError("peak equity cannot be below current equity")
        return cls(
            equity,
            peak,
            tuple(open_positions),
            ensure_utc(as_of),
            ensure_utc(last_loss_at) if last_loss_at else None,
        )

    @property
    def open_count(self) -> int:
        return len(self.open_positions)

    @property
    def open_exposure_quote(self) -> Decimal:
        return sum((p.exposure_quote for p in self.open_positions), Decimal(0))

    @property
    def drawdown_pct(self) -> Decimal:
        return (
            (self.peak_equity_quote - self.equity_quote)
            / self.peak_equity_quote
            * Decimal(100)
        )
