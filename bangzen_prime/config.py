from dataclasses import dataclass
from enum import Enum

class TradingMode(Enum):
    PAPER = "paper"
    LIVE = "live"

@dataclass
class BotConfig:
    buy_amount_sol: float = 0.1
    max_slippage_bps: int = 500
    priority_fee_lamports: int = 500_000
    ai_temperature: float = 0.3
    ai_entry_timeout_seconds: float = 5.0
    min_liquidity_usd: float = 1000.0
    max_position_age_minutes: int = 30

TRADING_PRESETS = {
    "default": {
        "buy_amount_sol": 0.1,
        "max_slippage_bps": 500,
        "stop_loss_pct": 25.0,
        "take_profit_pct": 100.0,
    },
    "sniper": {
        "buy_amount_sol": 0.05,
        "max_slippage_bps": 1000,
        "stop_loss_pct": 15.0,
        "take_profit_pct": 50.0,
    }
}
