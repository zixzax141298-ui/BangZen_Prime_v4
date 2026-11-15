import os
from dataclasses import dataclass
from enum import Enum


class TradingMode(Enum):
    PAPER = "paper"
    LIVE = "live"
    CONSERVATIVE = "conservative"
    DEGEN = "degen"


@dataclass
class BotConfig:
    """
    Jembatan Konfigurasi:
    Menghormati settingan BANGZEN (via .env) tapi memenuhi format FENRIR.
    """

    mode: TradingMode = TradingMode.PAPER
    buy_amount_sol: float = 0.1
    max_slippage_bps: int = 500
    priority_fee_lamports: int = 500_000
    ai_temperature: float = 0.3
    ai_entry_timeout_seconds: float = 5.0
    ai_min_confidence_to_buy: float = 0.6
    sniper_daily_budget_sol: float = 1.0
    stop_loss_pct: float = 25.0
    take_profit_pct: float = 100.0
    trailing_stop_pct: float = 15.0
    max_position_age_minutes: int = 30

    # --- JEMBATAN KE .ENV BANGZEN ---
    # Mengambil dari .env BANGZEN, kalau kosong pakai default publik
    rpc_url: str = os.getenv("BANGZEN_RPC_URL", "https://api.mainnet-beta.solana.com")
    ws_url: str = os.getenv("BANGZEN_WS_URL", "wss://api.mainnet-beta.solana.com")

    websocket_enabled: bool = True
    migration_feed_enabled: bool = False
    poll_interval_seconds: float = 5.0

    # ID Program Pump.fun (Wajib untuk FENRIR)
    pumpfun_program: str = "6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P"

    min_initial_liquidity_sol: float = 0.0
    max_initial_market_cap_sol: float = 500.0

    geyser_grpc_endpoint: str = ""
    geyser_x_token: str = ""
    geyser_commitment: str = "processed"

    @classmethod
    def from_mode(cls, mode: TradingMode) -> "BotConfig":
        return cls(mode=mode)


TRADING_PRESETS = {
    TradingMode.PAPER: {"ai_temperature": 0.3},
    TradingMode.CONSERVATIVE: {"ai_temperature": 0.1},
    TradingMode.DEGEN: {"ai_temperature": 0.7},
}
