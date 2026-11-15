"""Chronological development / validation / test split and walk-forward replay.

Design notes (see docs/STRATEGY_RESEARCH.md):
- Phases are contiguous index ranges over the candle series, in time order, so the test
  phase is strictly later than development and validation.
- A candidate belongs to the phase that contains its signal candle (candle_index). Its fill
  and exit are evaluated on the full series, because a trade opened in one phase is part of
  that phase's evidence even when it closes later. Nothing in the evaluation looks at data
  before the signal.
- Baselines use the same notional and cost model: buy-and-hold enters at the phase's first
  open and exits at the phase's last close; no-trade has zero PnL.
- Fold stability splits the test phase into contiguous folds. A fold without trades is
  "no evidence", not a pass.

This module does not tune parameters. It reports what a frozen configuration did.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from bangzen_prime.core.errors import DomainError
from bangzen_prime.research.backtesting import (
    BacktestConfig,
    BacktestReport,
    HistoricalCandle,
    TradeCandidate,
    evaluate_candidates,
)
from bangzen_prime.research.config_freeze import config_hash

ZERO = Decimal(0)
ONE = Decimal(1)


@dataclass(frozen=True)
class PhaseRange:
    name: str
    start: int  # inclusive candle index
    end: int  # exclusive candle index

    def __post_init__(self) -> None:
        if not self.name:
            raise DomainError("phase name must not be empty")
        if self.start < 0 or self.end <= self.start:
            raise DomainError(f"invalid phase range for {self.name}")

    def contains(self, candle_index: int) -> bool:
        return self.start <= candle_index < self.end


@dataclass(frozen=True)
class PhaseSplit:
    development: PhaseRange
    validation: PhaseRange
    test: PhaseRange

    def __post_init__(self) -> None:
        if self.development.start != 0:
            raise DomainError("development phase must start at candle 0")
        if self.development.end != self.validation.start:
            raise DomainError("phases must be contiguous (development -> validation)")
        if self.validation.end != self.test.start:
            raise DomainError("phases must be contiguous (validation -> test)")

    @property
    def ordered(self) -> tuple[PhaseRange, PhaseRange, PhaseRange]:
        return (self.development, self.validation, self.test)


def chronological_split(
    candle_count: int,
    development_fraction: Decimal = Decimal("0.5"),
    validation_fraction: Decimal = Decimal("0.25"),
    min_candles_per_phase: int = 20,
) -> PhaseSplit:
    """Split candle indexes into three contiguous phases in time order.

    The test phase receives the remainder, so it is always the latest data.
    """
    if isinstance(candle_count, bool) or not isinstance(candle_count, int):
        raise DomainError("candle_count must be an integer")
    if min_candles_per_phase < 2:
        raise DomainError("min_candles_per_phase must be >= 2")
    if candle_count < 3 * min_candles_per_phase:
        raise DomainError("not enough candles for three phases")
    for name, value in (
        ("development_fraction", development_fraction),
        ("validation_fraction", validation_fraction),
    ):
        if not isinstance(value, Decimal) or not value.is_finite() or value <= ZERO:
            raise DomainError(f"{name} must be a finite Decimal > 0")
    if development_fraction + validation_fraction >= ONE:
        raise DomainError("development + validation fractions must be < 1")

    dev_end = int(Decimal(candle_count) * development_fraction)
    val_end = int(Decimal(candle_count) * (development_fraction + validation_fraction))
    split = PhaseSplit(
        development=PhaseRange("development", 0, dev_end),
        validation=PhaseRange("validation", dev_end, val_end),
        test=PhaseRange("test", val_end, candle_count),
    )
    for phase in split.ordered:
        if phase.end - phase.start < min_candles_per_phase:
            raise DomainError(f"{phase.name} phase has fewer than {min_candles_per_phase} candles")
    return split


def buy_and_hold_net_pnl(
    candles: Sequence[HistoricalCandle], config: BacktestConfig
) -> Decimal:
    """Net PnL of one position held from the first open to the last close of the slice.

    Uses the same fee, slippage and fixed-cost rules as evaluate_candidates.
    """
    if len(candles) < 2:
        raise DomainError("buy-and-hold needs at least two candles")
    slip = config.slippage_rate_per_side
    fee = config.fee_rate_per_side
    entry_fill = candles[0].open * (ONE + slip)
    exit_fill = candles[-1].close * (ONE - slip)
    cash_in = config.position_notional * (ONE + fee) + config.fixed_cost_per_trade
    units = config.position_notional / entry_fill
    proceeds = units * exit_fill * (ONE - fee)
    return proceeds - cash_in


@dataclass(frozen=True)
class PhaseResult:
    phase: str
    start: int
    end: int
    candidate_count: int
    report: BacktestReport
    buy_and_hold_net_pnl: Decimal

    @property
    def trade_count(self) -> int:
        return len(self.report.trades)

    @property
    def strategy_net_pnl(self) -> Decimal:
        return sum((trade.net_pnl for trade in self.report.trades), ZERO)

    @property
    def no_trade_net_pnl(self) -> Decimal:
        return ZERO

    @property
    def beats_buy_and_hold(self) -> bool:
        return self.strategy_net_pnl > self.buy_and_hold_net_pnl

    @property
    def beats_no_trade(self) -> bool:
        return self.strategy_net_pnl > self.no_trade_net_pnl


@dataclass(frozen=True)
class FoldResult:
    index: int
    start: int
    end: int
    candidate_count: int
    trade_count: int
    expectancy_pct: Decimal | None  # None when the fold has no trades
    net_pnl: Decimal

    @property
    def is_positive(self) -> bool:
        return self.expectancy_pct is not None and self.expectancy_pct > ZERO


@dataclass(frozen=True)
class WalkForwardReport:
    config_hash: str
    split: PhaseSplit
    phases: tuple[PhaseResult, ...]
    folds: tuple[FoldResult, ...]

    def phase(self, name: str) -> PhaseResult:
        for result in self.phases:
            if result.phase == name:
                return result
        raise DomainError(f"unknown phase: {name}")

    @property
    def folds_with_trades(self) -> int:
        return sum(1 for fold in self.folds if fold.trade_count > 0)

    @property
    def positive_fold_ratio(self) -> Decimal | None:
        """Share of folds with positive expectancy, among folds that have trades."""
        if self.folds_with_trades == 0:
            return None
        positive = sum(1 for fold in self.folds if fold.is_positive)
        return Decimal(positive) / Decimal(self.folds_with_trades)


def _validate_candidates(
    candles: Sequence[HistoricalCandle], candidates: Sequence[TradeCandidate]
) -> None:
    ids = [candidate.candidate_id for candidate in candidates]
    if len(set(ids)) != len(ids):
        raise DomainError("candidate_id values must be unique across all phases")
    for candidate in candidates:
        if candidate.candle_index >= len(candles):
            raise DomainError(
                f"candidate {candidate.candidate_id} is outside the candle range"
            )


def run_walk_forward(
    candles: Sequence[HistoricalCandle],
    candidates: Sequence[TradeCandidate],
    config: BacktestConfig,
    split: PhaseSplit | None = None,
    fold_count: int = 4,
) -> WalkForwardReport:
    if split is None:
        split = chronological_split(len(candles))
    if split.test.end != len(candles):
        raise DomainError("split must cover every candle up to the last one")
    if isinstance(fold_count, bool) or not isinstance(fold_count, int) or fold_count < 2:
        raise DomainError("fold_count must be an integer >= 2")
    if split.test.end - split.test.start < fold_count:
        raise DomainError("test phase is shorter than fold_count")
    _validate_candidates(candles, candidates)

    phase_results: list[PhaseResult] = []
    for phase in split.ordered:
        phase_candidates = [c for c in candidates if phase.contains(c.candle_index)]
        report = evaluate_candidates(candles, phase_candidates, config)
        phase_results.append(
            PhaseResult(
                phase=phase.name,
                start=phase.start,
                end=phase.end,
                candidate_count=len(phase_candidates),
                report=report,
                buy_and_hold_net_pnl=buy_and_hold_net_pnl(
                    candles[phase.start : phase.end], config
                ),
            )
        )

    folds: list[FoldResult] = []
    test = split.test
    length = test.end - test.start
    bounds = [test.start + (length * i) // fold_count for i in range(fold_count + 1)]
    for index in range(fold_count):
        start, end = bounds[index], bounds[index + 1]
        fold_candidates = [c for c in candidates if start <= c.candle_index < end]
        report = evaluate_candidates(candles, fold_candidates, config)
        trades = len(report.trades)
        folds.append(
            FoldResult(
                index=index,
                start=start,
                end=end,
                candidate_count=len(fold_candidates),
                trade_count=trades,
                expectancy_pct=report.expectancy_pct if trades else None,
                net_pnl=sum((t.net_pnl for t in report.trades), ZERO),
            )
        )

    return WalkForwardReport(
        config_hash=config_hash(config),
        split=split,
        phases=tuple(phase_results),
        folds=tuple(folds),
    )
