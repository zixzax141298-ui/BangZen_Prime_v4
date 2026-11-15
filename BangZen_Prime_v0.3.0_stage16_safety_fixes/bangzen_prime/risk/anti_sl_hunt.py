import logging
from decimal import Decimal

logger = logging.getLogger(__name__)
DEFAULT_BUFFER_PCT = Decimal("2.5")


def calculate_safe_sl(
    swing_low, current_price, max_sl_pct, buffer_pct=DEFAULT_BUFFER_PCT
):
    if swing_low <= 0 or current_price <= 0:
        return max(Decimal(0), current_price * (1 - max_sl_pct / 100))
    cushioned_sl = swing_low * (1 - buffer_pct / 100)
    floor_price = current_price * (1 - max_sl_pct / 100)
    safe_sl = max(cushioned_sl, floor_price)
    if safe_sl >= current_price:
        safe_sl = floor_price
    return round(safe_sl, 8)
