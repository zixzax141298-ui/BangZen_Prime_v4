import logging
from dataclasses import dataclass
from decimal import Decimal
logger = logging.getLogger(__name__)
@dataclass(frozen=True)
class SlippageAdvice:
    slippage_bps: int
    use_mev_protection: bool
    risk_level: str
    advice: str
class DynamicSlippageEngine:
    def calculate(self, liquidity_usd, vol_ratio):
        liq = liquidity_usd if liquidity_usd > 0 else Decimal("0")
        vol = vol_ratio if vol_ratio > 0 else Decimal("0")
        if liq < Decimal("20000") and vol > Decimal("1.5"):
            return SlippageAdvice(2500, True, "EXTREME", "LP tipis, wajib Jito")
        if liq >= Decimal("20000"):
            if vol > Decimal("3.0"):
                return SlippageAdvice(1500, True, "MEDIUM", "Volume tinggi")
            return SlippageAdvice(1000, False, "LOW", "LP tebal")
        return SlippageAdvice(1500, True, "HIGH", "LP terbatas")
