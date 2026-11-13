import logging
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TWAPPlan:
    total_usd: Decimal
    slices: int
    slice_usd: Decimal
    interval_sec: int
    duration_minutes: int
    status: str


class TWAPExecutionEngine:
    def plan_slices(
        self, total_usd, liq_usd, duration_minutes=15, min_slices=3, max_slices=10
    ):
        if total_usd <= 0 or liq_usd <= 0:
            return TWAPPlan(total_usd, 1, total_usd, 0, duration_minutes, "trivial")
        max_safe_slice = max(Decimal("5.0"), liq_usd * Decimal("0.005"))
        raw_slices = (total_usd / max_safe_slice).to_integral_value(
            rounding=ROUND_CEILING
        )
        slices = max(min_slices, min(max_slices, int(raw_slices)))
        slice_usd = (total_usd / Decimal(str(slices))).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )
        interval_sec = int((duration_minutes * 60) / max(1, slices))
        return TWAPPlan(
            total_usd,
            slices,
            slice_usd,
            interval_sec,
            duration_minutes,
            "twap_optimized",
        )
