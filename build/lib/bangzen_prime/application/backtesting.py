"""Deterministic, cost-aware historical trade evaluation.

This module evaluates externally generated candidate plans. It does not invent entries,
fetch market data, or place orders. Signals are assumed to be known only after the
candidate candle closes; execution therefore starts at the next candle's open.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bangzen_prime.errors import DomainError

ZERO = Decimal(0)
ONE = Decimal(1)
HUNDRED = Decimal(100)


def _finite(value: Decimal, name: str) -> Decimal:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise DomainError(f"{name} must be a finite Decimal")
    return value


def _positive(value: Decimal, name: str) -> Decimal:
    result = _finite(value, name)
    if result <= ZERO:
        raise DomainError(f"{name} must be > 0")
    return result


def _fraction(value: Decimal, name: str) -> Decimal:
    result = _finite(value, name)
    if result < ZERO or result >= ONE:
        raise DomainError(f"{name} must be in [0, 1)")
    return result


@dataclass(frozen=True)
class HistoricalCandle:
    timestamp: datetime
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    def __post_init__(self) -> None:
        if (
            not isinstance(self.timestamp, datetime)
            or self.timestamp.tzinfo is None
            or self.timestamp.utcoffset() is None
        ):
            raise DomainError("candle timestamp must be timezone-aware")
        for name in ("open", "high", "low", "close"):
            _positive(getattr(self, name), name)
        _finite(self.volume, "volume")
        if self.volume < ZERO:
            raise DomainError("volume must be >= 0")
        if self.high < max(self.open, self.close, self.low):
            raise DomainError("candle high is inconsistent")
        if self.low > min(self.open, self.close, self.high):
            raise DomainError("candle low is inconsistent")


@dataclass(frozen=True)
class TradeCandidate:
    """A plan emitted at candle_index close; it can only fill on the next candle."""

    candidate_id: str
    candle_index: int
    stop_loss: Decimal
    take_profit: Decimal

    def __post_init__(self) -> None:
        if not self.candidate_id or not self.candidate_id.strip():
            raise DomainError("candidate_id must not be empty")
        if (
            isinstance(self.candle_index, bool)
            or not isinstance(self.candle_index, int)
            or self.candle_index < 0
        ):
            raise DomainError("candle_index must be an integer >= 0")
        _positive(self.stop_loss, "stop_loss")
        _positive(self.take_profit, "take_profit")
        if self.stop_loss >= self.take_profit:
            raise DomainError("stop_loss must be below take_profit")


@dataclass(frozen=True)
class BacktestConfig:
    initial_equity: Decimal = Decimal(1000)
    position_notional: Decimal = Decimal(100)
    fee_rate_per_side: Decimal = Decimal("0.001")
    slippage_rate_per_side: Decimal = Decimal("0.002")
    max_holding_candles: int = 60

    def __post_init__(self) -> None:
        _positive(self.initial_equity, "initial_equity")
        _positive(self.position_notional, "position_notional")
        _fraction(self.fee_rate_per_side, "fee_rate_per_side")
        _fraction(self.slippage_rate_per_side, "slippage_rate_per_side")
        if (
            isinstance(self.max_holding_candles, bool)
            or not isinstance(self.max_holding_candles, int)
            or self.max_holding_candles < 1
        ):
            raise DomainError("max_holding_candles must be an integer >= 1")
        if self.position_notional > self.initial_equity:
            raise DomainError("position_notional must not exceed initial_equity")


@dataclass(frozen=True)
class BacktestTrade:
    candidate_id: str
    entry_time: datetime
    exit_time: datetime
    entry_fill: Decimal
    exit_fill: Decimal
    exit_reason: str
    gross_return_pct: Decimal
    net_return_pct: Decimal
    net_pnl: Decimal


@dataclass(frozen=True)
class BacktestReport:
    trades: tuple[BacktestTrade, ...]
    initial_equity: Decimal
    final_equity: Decimal
    total_return_pct: Decimal
    win_rate_pct: Decimal
    expectancy_pct: Decimal
    profit_factor: Decimal | None
    max_drawdown_pct: Decimal
    wins: int
    losses: int
    breakeven: int
    rejected_candidates: int


def _validate_series(candles: Sequence[HistoricalCandle]) -> None:
    if len(candles) < 2:
        raise DomainError("at least two candles are required")
    previous = None
    for candle in candles:
        if not isinstance(candle, HistoricalCandle):
            raise DomainError("candles must contain HistoricalCandle values")
        if previous is not None and candle.timestamp <= previous:
            raise DomainError("candle timestamps must be strictly increasing")
        previous = candle.timestamp


def _evaluate_one(
    candidate: TradeCandidate,
    candles: Sequence[HistoricalCandle],
    config: BacktestConfig,
) -> BacktestTrade | None:
    # Signal at candle close: no same-candle fill, avoiding look-ahead bias.
    start = candidate.candle_index + 1
    if start >= len(candles):
        return None
    entry_bar = candles[start]
    raw_entry = entry_bar.open
    if raw_entry <= candidate.stop_loss or raw_entry >= candidate.take_profit:
        return None
    entry_fill = raw_entry * (ONE + config.slippage_rate_per_side)
    if entry_fill >= candidate.take_profit:
        return None
    end = min(len(candles), start + config.max_holding_candles)
    exit_bar = candles[end - 1]
    raw_exit = exit_bar.close
    exit_reason = "TIME_EXIT"

    for bar in candles[start:end]:
        hit_stop = bar.low <= candidate.stop_loss
        hit_target = bar.high >= candidate.take_profit
        # OHLC does not reveal intrabar ordering; assume the adverse stop if both hit.
        if hit_stop:
            raw_exit = min(bar.open, candidate.stop_loss)
            exit_bar = bar
            exit_reason = "STOP_LOSS"
            break
        if hit_target:
            raw_exit = candidate.take_profit
            exit_bar = bar
            exit_reason = "TAKE_PROFIT"
            break

    exit_fill = raw_exit * (ONE - config.slippage_rate_per_side)
    entry_cost = config.position_notional * (ONE + config.fee_rate_per_side)
    units = config.position_notional / entry_fill
    exit_proceeds = units * exit_fill * (ONE - config.fee_rate_per_side)
    net_pnl = exit_proceeds - entry_cost
    net_return = (net_pnl / entry_cost) * HUNDRED
    gross_return = ((raw_exit / raw_entry) - ONE) * HUNDRED
    return BacktestTrade(
        candidate_id=candidate.candidate_id,
        entry_time=entry_bar.timestamp,
        exit_time=exit_bar.timestamp,
        entry_fill=entry_fill,
        exit_fill=exit_fill,
        exit_reason=exit_reason,
        gross_return_pct=gross_return,
        net_return_pct=net_return,
        net_pnl=net_pnl,
    )


def evaluate_candidates(
    candles: Sequence[HistoricalCandle],
    candidates: Sequence[TradeCandidate],
    config: BacktestConfig = BacktestConfig(),
) -> BacktestReport:
    """Replay candidate plans with next-open fills, costs and conservative stops.

    Each candidate is evaluated independently at a fixed notional. This first version
    intentionally does not model concurrent capital allocation, partial fills, MEV,
    priority fees, token taxes, failed transactions, or liquidity impact; users must not
    interpret it as a production execution simulator.
    """
    _validate_series(candles)
    if len({candidate.candidate_id for candidate in candidates}) != len(candidates):
        raise DomainError("candidate_id values must be unique")
    trades: list[BacktestTrade] = []
    rejected = 0
    for candidate in candidates:
        if candidate.candle_index >= len(candles) - 1:
            rejected += 1
            continue
        trade = _evaluate_one(candidate, candles, config)
        if trade is None:
            rejected += 1
        else:
            trades.append(trade)

    equity = config.initial_equity
    peak = equity
    max_drawdown = ZERO
    wins = losses = breakeven = 0
    gross_profit = gross_loss = ZERO
    returns: list[Decimal] = []
    for trade in trades:
        equity += trade.net_pnl
        peak = max(peak, equity)
        if peak > ZERO:
            max_drawdown = max(max_drawdown, (peak - equity) / peak * HUNDRED)
        returns.append(trade.net_return_pct)
        if trade.net_pnl > ZERO:
            wins += 1
            gross_profit += trade.net_pnl
        elif trade.net_pnl < ZERO:
            losses += 1
            gross_loss += abs(trade.net_pnl)
        else:
            breakeven += 1

    count = len(trades)
    win_rate = Decimal(wins) / Decimal(count) * HUNDRED if count else ZERO
    expectancy = sum(returns, ZERO) / Decimal(count) if count else ZERO
    profit_factor = gross_profit / gross_loss if gross_loss > ZERO else None
    total_return = (equity / config.initial_equity - ONE) * HUNDRED
    return BacktestReport(
        trades=tuple(trades),
        initial_equity=config.initial_equity,
        final_equity=equity,
        total_return_pct=total_return,
        win_rate_pct=win_rate,
        expectancy_pct=expectancy,
        profit_factor=profit_factor,
        max_drawdown_pct=max_drawdown,
        wins=wins,
        losses=losses,
        breakeven=breakeven,
        rejected_candidates=rejected,
    )
