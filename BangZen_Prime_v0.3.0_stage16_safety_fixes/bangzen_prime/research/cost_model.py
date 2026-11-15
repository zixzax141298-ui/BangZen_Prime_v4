"""Explicit execution cost model for research backtests.

Rules (AI_RULES non_negotiable_safety, evidence_contract):
- A cost that was not measured is UNAVAILABLE and names the missing inputs. It is never
  defaulted to zero, false, or "safe".
- An input that is present but invalid (negative, non-finite, failure rate >= 1) raises
  DomainError. Invalid configuration is not silently repaired.
- The model is an assumption, not a measurement. Its output must be reported as such.

Research-only: this module sends no transactions and reads no market data.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bangzen_prime.core.errors import DomainError
from bangzen_prime.research.backtesting import BacktestConfig

ZERO = Decimal(0)
ONE = Decimal(1)

AVAILABLE = "AVAILABLE"
UNAVAILABLE = "UNAVAILABLE"

# A round trip is one entry transaction and one exit transaction, and each one pays a
# priority fee. The value is a modelling assumption and is kept here, not hidden in code.
TRANSACTIONS_PER_ROUND_TRIP = 2


def _require_finite_nonnegative(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise DomainError(f"{name} must be a finite Decimal")
    if value < ZERO:
        raise DomainError(f"{name} must be >= 0")
    return value


@dataclass(frozen=True)
class CostInputs:
    """Inputs for the model. None means the value was not measured or not provided."""

    notional: Decimal
    fee_rate_per_side: Decimal | None = None
    base_slippage_rate: Decimal | None = None
    liquidity_quote: Decimal | None = None
    impact_coefficient: Decimal | None = None
    priority_fee_quote: Decimal | None = None
    tx_failure_rate: Decimal | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.notional, Decimal) or self.notional <= ZERO:
            raise DomainError("notional must be a Decimal > 0")
        for name in (
            "fee_rate_per_side",
            "base_slippage_rate",
            "liquidity_quote",
            "impact_coefficient",
            "priority_fee_quote",
            "tx_failure_rate",
        ):
            value = getattr(self, name)
            if value is not None:
                _require_finite_nonnegative(value, name)
        if self.tx_failure_rate is not None and self.tx_failure_rate >= ONE:
            raise DomainError("tx_failure_rate must be in [0, 1)")


@dataclass(frozen=True)
class CostEstimate:
    status: str
    missing: tuple[str, ...]
    fee_rate_per_side: Decimal | None
    slippage_rate_per_side: Decimal | None
    expected_fixed_cost_per_trade: Decimal | None
    notes: tuple[str, ...] = ()

    @property
    def is_available(self) -> bool:
        return self.status == AVAILABLE

    def to_backtest_config(
        self,
        initial_equity: Decimal,
        position_notional: Decimal,
        max_holding_candles: int,
    ) -> BacktestConfig:
        """Build a BacktestConfig. Refuses to build one from an UNAVAILABLE estimate."""
        if not self.is_available:
            raise DomainError(
                "cost estimate is UNAVAILABLE; missing inputs: " + ", ".join(self.missing)
            )
        assert self.fee_rate_per_side is not None
        assert self.slippage_rate_per_side is not None
        assert self.expected_fixed_cost_per_trade is not None
        return BacktestConfig(
            initial_equity=initial_equity,
            position_notional=position_notional,
            fee_rate_per_side=self.fee_rate_per_side,
            slippage_rate_per_side=self.slippage_rate_per_side,
            max_holding_candles=max_holding_candles,
            fixed_cost_per_trade=self.expected_fixed_cost_per_trade,
        )


def estimate_costs(inputs: CostInputs) -> CostEstimate:
    """Compute per-side rates and the expected fixed cost per round trip.

    Slippage: base_slippage_rate + impact_coefficient * (notional / liquidity_quote).
    This linear impact term is a simplification. It is not a calibrated price-impact curve.

    Priority fees: each transaction is attempted until it succeeds. With a failure rate p,
    the expected number of attempts per success is 1 / (1 - p). The fixed cost per round
    trip is TRANSACTIONS_PER_ROUND_TRIP * priority_fee / (1 - p).
    """
    missing: list[str] = []

    if inputs.fee_rate_per_side is None:
        missing.append("fee_rate_per_side")
    if inputs.base_slippage_rate is None:
        missing.append("base_slippage_rate")
    if inputs.liquidity_quote is None or inputs.liquidity_quote <= ZERO:
        missing.append("liquidity_quote(>0)")
    if inputs.impact_coefficient is None:
        missing.append("impact_coefficient")
    if inputs.priority_fee_quote is None:
        missing.append("priority_fee_quote")
    if inputs.tx_failure_rate is None:
        missing.append("tx_failure_rate")

    if missing:
        return CostEstimate(
            status=UNAVAILABLE,
            missing=tuple(missing),
            fee_rate_per_side=None,
            slippage_rate_per_side=None,
            expected_fixed_cost_per_trade=None,
        )

    assert inputs.fee_rate_per_side is not None
    assert inputs.base_slippage_rate is not None
    assert inputs.liquidity_quote is not None
    assert inputs.impact_coefficient is not None
    assert inputs.priority_fee_quote is not None
    assert inputs.tx_failure_rate is not None

    slippage = inputs.base_slippage_rate + inputs.impact_coefficient * (
        inputs.notional / inputs.liquidity_quote
    )
    if slippage >= ONE or inputs.fee_rate_per_side >= ONE:
        raise DomainError("fee or slippage rate must be < 1")
    attempts_factor = ONE / (ONE - inputs.tx_failure_rate)
    fixed = TRANSACTIONS_PER_ROUND_TRIP * inputs.priority_fee_quote * attempts_factor
    return CostEstimate(
        status=AVAILABLE,
        missing=(),
        fee_rate_per_side=inputs.fee_rate_per_side,
        slippage_rate_per_side=slippage,
        expected_fixed_cost_per_trade=fixed,
        notes=(
            "linear impact model (assumption, not calibrated)",
            "failed attempts pay priority fee; expected attempts = 1/(1-p)",
            "tips, MEV, token taxes and price-impact curves are not modelled",
        ),
    )
