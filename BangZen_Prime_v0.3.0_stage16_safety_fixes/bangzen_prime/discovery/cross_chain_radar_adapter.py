import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any

import httpx

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CrossChainCopycatReport:
    is_copycat: bool
    reason: str
    solana_symbol: str = ""
    evm_symbol: str = ""


class CrossChainRadarAdapter:
    def __init__(
        self,
        transport: httpx.AsyncClient,
        clock: Callable[[], datetime],
        cache_ttl_sec: int = 300,
    ):
        self.transport = transport
        self.clock = clock
        self.cache_ttl_sec = cache_ttl_sec
        self._evm_cache: dict[str, Any] = {"ts": 0.0, "symbols": []}

    def _normalize(self, s: str) -> str:
        return re.sub(r"[^A-Za-z0-9]", "", str(s)).upper()

    async def fetch_trending(self) -> tuple[str, ...]:
        now_ts = self.clock().timestamp()
        if self._evm_cache["symbols"] and (
            now_ts - self._evm_cache["ts"] < self.cache_ttl_sec
        ):
            return tuple(self._evm_cache["symbols"])

        trending = []
        try:
            resp = await self.transport.get(
                "https://api.dexscreener.com/latest/dex/tokens/trending", timeout=5.0
            )
            if resp.status_code == 200:
                for p in resp.json().get("pairs", []):
                    if str(p.get("chainId", "")).lower() in (
                        "ethereum",
                        "base",
                        "arbitrum",
                        "bsc",
                    ):
                        trending.append(
                            self._normalize(p.get("baseToken", {}).get("symbol", ""))
                        )
        except Exception:
            pass  # nosec B110

        self._evm_cache = {"ts": now_ts, "symbols": list(set(trending))}
        return tuple(self._evm_cache["symbols"])

    async def check_copycat(
        self, solana_symbol: str, age_min: Decimal
    ) -> CrossChainCopycatReport:
        sol = self._normalize(solana_symbol)
        if age_min >= Decimal("5.0"):
            return CrossChainCopycatReport(False, "mature_enough", sol)

        for evm in await self.fetch_trending():
            if sol == evm or (len(sol) >= 4 and (sol in evm or evm in sol)):
                return CrossChainCopycatReport(True, f"impersonates_{evm}", sol, evm)

        return CrossChainCopycatReport(False, "clean", sol)
