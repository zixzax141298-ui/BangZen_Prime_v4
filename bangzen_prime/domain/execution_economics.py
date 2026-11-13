"""Deterministic round-trip execution cost and net-expectancy arithmetic.

All monetary inputs MUST be normalized into the same quote currency and scale.
Expected exit value is gross, before the explicit costs below. No provider I/O,
token-decimal conversion, sizing, policy selection, signing, or execution occurs here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from bangzen_prime.domain.values import non_negative, positive
from bangzen_prime.errors import DomainError

ZERO = Decimal(0)


@dataclass(frozen=True)
class ExecutionCostBreakdown:
    """Explicit quote-currency costs for one complete entry/exit lifecycle."""

    entry_fee_quote: Decimal = field(default_factory=lambda: ZERO)
    exit_fee_quote: Decimal = field(default_factory=lambda: ZERO)
    entry_slippage_quote: Decimal = field(default_factory=lambda: ZERO)
    exit_slippage_quote: Decimal = field(default_factory=lambda: ZERO)
    entry_price_impact_quote: Decimal = field(default_factory=lambda: ZERO)
    exit_price_impact_quote: Decimal = field(default_factory=lambda: ZERO)
    priority_fee_quote: Decimal = field(default_factory=lambda: ZERO)
    jito_tip_quote: Decimal = field(default_factory=lambda: ZERO)
    rent_reserve_quote: Decimal = field(default_factory=lambda: ZERO)
    failed_exit_reserve_quote: Decimal = field(default_factory=lambda: ZERO)
    other_cost_quote: Decimal = field(default_factory=lambda: ZERO)

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            object.__setattr__(self, name, non_negative(getattr(self, name), name))

    @property
    def total_quote(self) -> Decimal:
        return sum((getattr(self, name) for name in self.__dataclass_fields__), ZERO)


@dataclass(frozen=True)
class NetExecutionEconomics:
    entry_notional_quote: Decimal
    expected_exit_gross_quote: Decimal
    costs: ExecutionCostBreakdown
    gross_pnl_quote: Decimal
    total_cost_quote: Decimal
    net_pnl_quote: Decimal
    break_even_exit_gross_quote: Decimal
    net_return_pct: Decimal
    total_cost_pct: Decimal

    @property
    def net_profitable(self) -> bool:
        return self.net_pnl_quote > ZERO


def calculate_net_execution_economics(
    *,
    entry_notional_quote: object,
    expected_exit_gross_quote: object,
    costs: ExecutionCostBreakdown,
) -> NetExecutionEconomics:
    """Calculate net PnL after all explicit round-trip costs.

    The caller must ensure the gross exit estimate does not already subtract any
    cost represented in costs, otherwise costs would be double-counted.
    """
    entry = positive(entry_notional_quote, "entry_notional_quote")
    exit_gross = positive(expected_exit_gross_quote, "expected_exit_gross_quote")
    if not isinstance(costs, ExecutionCostBreakdown):
        raise DomainError("costs must be a validated ExecutionCostBreakdown")
    total_cost = costs.total_quote
    gross_pnl = exit_gross - entry
    net_pnl = gross_pnl - total_cost
    break_even = entry + total_cost
    return NetExecutionEconomics(
        entry_notional_quote=entry,
        expected_exit_gross_quote=exit_gross,
        costs=costs,
        gross_pnl_quote=gross_pnl,
        total_cost_quote=total_cost,
        net_pnl_quote=net_pnl,
        break_even_exit_gross_quote=break_even,
        net_return_pct=net_pnl / entry * Decimal(100),
        total_cost_pct=total_cost / entry * Decimal(100),
    )
