"""DexScreener latest token-profile discovery feed.

This is a candidate source, not a complete Solana launch feed or a quality signal.
Every returned mint must still pass the existing market and RugCheck pipeline.
"""

from __future__ import annotations

import logging

from bangzen_prime.domain.tokens import validate_mint
from bangzen_prime.errors import DomainError, ExternalServiceError
from bangzen_prime.infrastructure.http import Transport, get_json
from bangzen_prime.infrastructure.resilience.policies import ResilientCaller

logger = logging.getLogger("bangzen_prime.dexscreener_discovery")
SERVICE = "dexscreener_discovery"


class DexScreenerDiscoveryAdapter:
    """Fetch latest token profiles and return unique, valid Solana mints."""

    def __init__(
        self,
        *,
        base_url: str,
        transport: Transport,
        caller: ResilientCaller,
        timeout: float,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._transport = transport
        self._caller = caller
        self._timeout = timeout

    def fetch_candidates(self, limit: int = 30) -> list[str]:
        if not 1 <= limit <= 100:
            raise ValueError("discovery limit must be within [1, 100]")
        url = f"{self._base}/token-profiles/latest/v1"
        data = self._caller.call(
            lambda: get_json(
                service=SERVICE,
                url=url,
                timeout=self._timeout,
                transport=self._transport,
            )
        )
        if not isinstance(data, list):
            raise ExternalServiceError(
                "DexScreener discovery returned an unexpected payload",
                service=SERVICE,
                retryable=False,
            )

        candidates: list[str] = []
        seen: set[str] = set()
        skipped = 0
        for item in data:
            if not isinstance(item, dict) or item.get("chainId") != "solana":
                skipped += 1
                continue
            mint = item.get("tokenAddress")
            try:
                validate_mint(mint)
            except DomainError:
                skipped += 1
                continue
            if mint not in seen:
                seen.add(mint)
                candidates.append(mint)
            if len(candidates) >= limit:
                break
        if skipped:
            logger.info("DexScreener discovery skipped %d unsupported or invalid entries", skipped)
        return candidates
