from dataclasses import dataclass
from enum import Enum


class TradingMode(Enum):
    PAPER = "paper"
    LIVE = "live"
    CONSERVATIVE = "conservative"
    DEGEN = "degen"


@dataclass
class BotConfig:
    # TAMBAHAN: Atribut mode yang dicari oleh Sniper
    mode: TradingMode = TradingMode.PAPER

    buy_amount_sol: float = 0.1
    max_slippage_bps: int = 500
    priority_fee_lamports: int = 500_000
    ai_temperature: float = 0.3
    ai_entry_timeout_seconds: float = 5.0

    # Atribut khusus Sniper
    sniper_daily_budget_sol: float = 1.0
    stop_loss_pct: float = 25.0
    take_profit_pct: float = 100.0
    trailing_stop_pct: float = 15.0
    max_position_age_minutes: int = 30
    ai_min_confidence_to_buy: float = 0.6

    @classmethod
    def from_mode(cls, mode: TradingMode) -> "BotConfig":
        return cls(mode=mode)


# Preset berdasarkan mode
TRADING_PRESETS = {
    TradingMode.PAPER: {"ai_temperature": 0.3},
    TradingMode.CONSERVATIVE: {"ai_temperature": 0.1},
    TradingMode.DEGEN: {"ai_temperature": 0.7},
}
