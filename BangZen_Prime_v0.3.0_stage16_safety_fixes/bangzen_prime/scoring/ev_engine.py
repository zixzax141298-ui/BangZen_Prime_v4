import logging
from dataclasses import dataclass
from decimal import Decimal

from bangzen_prime.scoring.ev_model import validate_trade_plan

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EVSimulationResult:
    entry: Decimal
    stop_loss: Decimal
    take_profit: Decimal
    position_size_usd: Decimal
    expected_value: Decimal
    is_executed: bool
    reason: str


class EVEngine:
    """
    Mesin Eksekusi berbasis Expected Value (EV) dan Position Sizing.
    Diadopsi dari logika inti Bangzen v2.
    """

    def __init__(
        self, equity_usd: Decimal = Decimal(1000), risk_pct: Decimal = Decimal("1.5")
    ):
        self.equity_usd = equity_usd
        self.risk_pct = risk_pct

    def simulate_entry(
        self,
        entry_price: Decimal,
        sl_price: Decimal,
        tp_price: Decimal,
        cost_pct: Decimal = Decimal("2.5"),
    ) -> EVSimulationResult:
        """Menjalankan simulasi EV dan Position Sizing sebelum 'membeli'."""

        # 1. Validasi EV (Menggunakan logika Bangzen v2 dari ev_model.py)
        validation = validate_trade_plan(entry_price, sl_price, tp_price, cost_pct)
        if not validation.is_valid:
            logger.info(f"[EV ENGINE] Rejected: {validation.reason}")
            return EVSimulationResult(
                entry_price,
                sl_price,
                tp_price,
                Decimal(0),
                validation.expected_value,
                False,
                validation.reason,
            )

        # 2. Hitung Position Size berdasarkan Risk
        risk_budget_usd = self.equity_usd * (self.risk_pct / Decimal(100))
        sl_distance_pct = ((entry_price - sl_price) / entry_price) * Decimal(100)

        # Kalkulasi total risiko (SL + Fee)
        total_risk_pct = sl_distance_pct + cost_pct

        if total_risk_pct == 0:
            return EVSimulationResult(
                entry_price,
                sl_price,
                tp_price,
                Decimal(0),
                validation.expected_value,
                False,
                "INVALID_RISK",
            )

        # Posisi USD = Budget Risiko / Total Risiko (%)
        pos_size_usd = risk_budget_usd / (total_risk_pct / Decimal(100))

        # Jangan sampai posisi melebihi equity
        pos_size_usd = min(pos_size_usd, self.equity_usd)

        logger.info(
            f"[EV ENGINE] Entry: {entry_price:.6f}, SL: {sl_price:.6f}, TP: {tp_price:.6f}"
        )
        logger.info(
            f"[EV ENGINE] EV: {validation.expected_value}, Net RR: {validation.net_rr}"
        )
        logger.info(f"[EV ENGINE] Calculated Position Size: ${pos_size_usd:.2f}")

        return EVSimulationResult(
            entry_price,
            sl_price,
            tp_price,
            pos_size_usd,
            validation.expected_value,
            True,
            "EXECUTED",
        )
