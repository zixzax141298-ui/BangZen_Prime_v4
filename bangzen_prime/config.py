from dataclasses import dataclass

@dataclass
class BotConfig:
    buy_amount_sol: float = 0.1
    max_slippage_bps: int = 500
    priority_fee_lamports: int = 500_000
    ai_temperature: float = 0.3
    ai_entry_timeout_seconds: float = 5.0
    min_liquidity_usd: float = 1000.0
    max_position_age_minutes: int = 30
