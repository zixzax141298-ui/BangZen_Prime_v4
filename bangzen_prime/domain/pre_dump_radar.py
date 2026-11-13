import logging
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_DEV_OUTFLOW_THRESHOLD = Decimal("0.5")
DEFAULT_SELL_SPIKE_RATIO = Decimal("2.5")
LP_DRAIN_THRESHOLD_PCT = Decimal("25.0")
SELL_VELOCITY_MIN_COUNT = 15


@dataclass(frozen=True)
class PreDumpReport:
    is_dump_imminent: bool
    reason: str
    drain_pct: Decimal = Decimal(0)
    dev_sell_pct: Decimal = Decimal(0)
    sell_ratio: Decimal = Decimal(0)


class PreDumpRadar:
    """
    Radar deteksi dump institusional sebelum terjadi.
    Mendeteksi: LP Drain, Dev Outflow, dan Sell Velocity Spike.
    """

    def __init__(
        self,
        dev_outflow_threshold: Decimal = DEFAULT_DEV_OUTFLOW_THRESHOLD,
        sell_spike_ratio: Decimal = DEFAULT_SELL_SPIKE_RATIO,
    ):
        self.dev_outflow_threshold = dev_outflow_threshold
        self.sell_spike_ratio = sell_spike_ratio

    def _safe_decimal(self, value: Any) -> Decimal:
        try:
            if value is None:
                return Decimal(0)
            return Decimal(str(value))
        except (InvalidOperation, ValueError):
            return Decimal(0)

    def analyze(
        self,
        current_liq: Decimal,
        initial_liq: Decimal,
        recent_dev_sell_pct: Decimal,
        buys_m5: int,
        sells_m5: int,
    ) -> PreDumpReport:
        # 1. Deteksi LP Drain
        if initial_liq > Decimal(0) and current_liq > Decimal(0):
            drain_pct = ((initial_liq - current_liq) / initial_liq) * Decimal(100)
            if drain_pct >= LP_DRAIN_THRESHOLD_PCT:
                return PreDumpReport(
                    is_dump_imminent=True,
                    reason=f"lp_drain_detected_{drain_pct:.1f}%",
                    drain_pct=drain_pct.quantize(Decimal("0.01")),
                )

        # 2. Deteksi Dev Outflow
        if recent_dev_sell_pct > self.dev_outflow_threshold:
            return PreDumpReport(
                is_dump_imminent=True,
                reason=f"dev_dump_outflow_{recent_dev_sell_pct:.2f}%",
                dev_sell_pct=recent_dev_sell_pct.quantize(Decimal("0.01")),
            )

        # 3. Deteksi Sell Velocity Spike
        if sells_m5 > SELL_VELOCITY_MIN_COUNT:
            buys_safe = max(buys_m5, 1)
            ratio = Decimal(str(sells_m5)) / Decimal(str(buys_safe))
            if ratio >= self.sell_spike_ratio:
                return PreDumpReport(
                    is_dump_imminent=True,
                    reason=f"sell_velocity_spike_{ratio:.2f}x",
                    sell_ratio=ratio.quantize(Decimal("0.01")),
                )

        return PreDumpReport(is_dump_imminent=False, reason="normal_flow")

    def analyze_market_dict(
        self, market: dict[str, Any], audit: dict[str, Any]
    ) -> PreDumpReport:
        """Helper untuk menganalisa langsung dari dict market/audit."""
        txns_m5 = market.get("txns_m5", {})
        buys, sells = 0, 0
        if isinstance(txns_m5, dict):
            buys = int(self._safe_decimal(txns_m5.get("buys", 0)))
            sells = int(self._safe_decimal(txns_m5.get("sells", 0)))

        current_liq = self._safe_decimal(market.get("liq"))
        initial_liq = self._safe_decimal(market.get("initial_liq")) or current_liq
        dev_sell = self._safe_decimal(audit.get("recent_dev_sell_pct"))

        return self.analyze(
            current_liq=current_liq,
            initial_liq=initial_liq,
            recent_dev_sell_pct=dev_sell,
            buys_m5=buys,
            sells_m5=sells,
        )
