#!/usr/bin/env python3
"""BANGZEN PRIME - Strategy Base Class"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TradeParams:
    buy_amount_sol: float = 0.1
    max_slippage_bps: int = 500
    stop_loss_pct: float = 25.0
    take_profit_pct: float = 100.0
    trailing_stop_pct: float = 15.0
    max_position_age_minutes: int = 30
    priority_fee_lamports: int = 500_000
    ai_min_confidence: float = 0.6
    ai_temperature: float = 0.3
    ai_entry_timeout: float = 5.0

    def to_dict(self) -> dict:
        return {
            "buy_amount_sol": self.buy_amount_sol,
            "max_slippage_bps": self.max_slippage_bps,
            "stop_loss_pct": self.stop_loss_pct,
            "take_profit_pct": self.take_profit_pct,
            "trailing_stop_pct": self.trailing_stop_pct,
            "max_position_age_minutes": self.max_position_age_minutes,
            "priority_fee_lamports": self.priority_fee_lamports,
            "ai_min_confidence": self.ai_min_confidence,
            "ai_temperature": self.ai_temperature,
        }


@dataclass
class StrategyState:
    active: bool = True
    paused: bool = False
    positions_open: int = 0
    sol_spent_today: float = 0.0
    trades_today: int = 0
    wins_today: int = 0
    losses_today: int = 0

    @property
    def win_rate_today(self) -> float:
        total = self.wins_today + self.losses_today
        return self.wins_today / total if total > 0 else 0.0


class TradingStrategy(ABC):
    strategy_id: str = "bangzen_base"
    display_name: str = "Bangzen Base Strategy"
    description: str = ""
    uses_market_data: bool = False
    budget_sol: float = 1.0
    max_concurrent_positions: int = 3
    state: StrategyState = field(default_factory=StrategyState)

    def __init__(self):
        self.state = StrategyState()

    @abstractmethod
    async def should_evaluate(self, token_data: dict) -> bool:
        pass

    @abstractmethod
    def get_ai_context(self) -> str:
        pass

    @abstractmethod
    def get_trade_params(self) -> TradeParams:
        pass

    def evaluate_token(self, token_data: dict, market_data: Any = None) -> Any:
        return None

    def can_open_position(self) -> bool:
        if self.state.paused or not self.state.active:
            return False
        if self.state.positions_open >= self.max_concurrent_positions:
            return False
        return True

    def can_spend(self, amount_sol: float) -> bool:
        return (self.state.sol_spent_today + amount_sol) <= self.budget_sol

    def record_spend(self, amount_sol: float) -> None:
        self.state.sol_spent_today += amount_sol
        self.state.trades_today += 1
        self.state.positions_open += 1

    def record_close(self, pnl_pct: float) -> None:
        self.state.positions_open = max(0, self.state.positions_open - 1)
        if pnl_pct > 0:
            self.state.wins_today += 1
        else:
            self.state.losses_today += 1

    def get_status(self) -> dict:
        return {
            "strategy_id": self.strategy_id,
            "active": self.state.active,
            "budget_remaining": self.budget_sol - self.state.sol_spent_today,
            "positions_open": self.state.positions_open,
            "win_rate_today": self.state.win_rate_today,
        }
