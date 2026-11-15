import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LPSniperReport:
    is_whale_backed: bool
    signal: str
    token: str = ""
    age_min: Decimal | None = None
    liq_usd: Decimal = Decimal(0)
    reason: str = ""


class LPSniperAdapter:
    def __init__(
        self,
        transport: httpx.AsyncClient,
        clock: Callable[[], datetime],
        lp_threshold: Decimal = Decimal(30000),
    ):
        self.transport = transport
        self.clock = clock
        self.lp_threshold = lp_threshold
        self._alerted: set[str] = set()

    async def check_token(self, token_address: str, age_min: Decimal) -> LPSniperReport:
        if age_min > Decimal("15.0"):
            return LPSniperReport(False, "too_old", token_address)

        try:
            resp = await self.transport.get(
                f"https://api.dexscreener.com/latest/dex/tokens/{token_address}",
                timeout=5.0,
            )
            if resp.status_code != 200:
                return LPSniperReport(False, "api_error", token_address)

            pairs = resp.json().get("pairs", [])
            if not pairs:
                return LPSniperReport(False, "no_pairs", token_address)

            best_pair = max(
                pairs,
                key=lambda p: float((p.get("liquidity") or {}).get("usd", 0) or 0),
            )
            liq = Decimal(str((best_pair.get("liquidity") or {}).get("usd", 0)))

            if liq >= self.lp_threshold and token_address not in self._alerted:
                self._alerted.add(token_address)
                return LPSniperReport(
                    True, "WHALE_BACKING", token_address, age_min, liq, "lp_spike"
                )

            return LPSniperReport(False, "below_threshold", token_address, age_min, liq)
        except Exception as e:
            return LPSniperReport(False, f"error_{e}", token_address)
