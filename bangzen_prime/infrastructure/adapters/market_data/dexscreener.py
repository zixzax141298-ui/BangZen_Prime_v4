"""DexScreener adapter. Pair observations include optional pairCreatedAt lifecycle evidence."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import quote

from bangzen_prime.domain.tokens import PairSnapshot, validate_chain, validate_mint
from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.adapters.market_data.parsing import (
    MalformedData,
    require_str,
    to_decimal,
)
from bangzen_prime.infrastructure.http import Transport, get_json
from bangzen_prime.infrastructure.resilience.policies import ResilientCaller

logger = logging.getLogger("bangzen_prime.dexscreener")
SERVICE = "dexscreener"


class DexScreenerAdapter:
    def __init__(
        self,
        *,
        base_url: str,
        transport: Transport,
        caller: ResilientCaller,
        timeout: float,
        clock: Callable[[], datetime],
    ) -> None:
        self._base = base_url.rstrip("/")
        self._transport = transport
        self._caller = caller
        self._timeout = timeout
        self._clock = clock

    def fetch_pairs(self, chain: str, mint: str) -> list[PairSnapshot]:
        validate_chain(chain)
        validate_mint(mint)
        url = f"{self._base}/token-pairs/v1/{quote(chain, safe='')}/{quote(mint, safe='')}"
        data = self._caller.call(
            lambda: get_json(
                service=SERVICE,
                url=url,
                timeout=self._timeout,
                transport=self._transport,
            )
        )
        if not isinstance(data, list):
            raise MalformedData(SERVICE, "expected a list of pairs")
        now = self._clock()
        snapshots: list[PairSnapshot] = []
        skipped = 0
        for item in data:
            try:
                snapshots.append(self._parse_pair(item, chain, mint, now))
            except (MalformedData, DomainError):
                skipped += 1
        if skipped:
            logger.warning(
                "dexscreener skipped %d malformed or foreign pair entries", skipped
            )
        return snapshots

    @staticmethod
    def _pair_created_at(item: dict[str, Any]) -> datetime | None:
        raw = item.get("pairCreatedAt")
        if isinstance(raw, bool) or not isinstance(raw, (int, float)):
            return None
        try:
            timestamp = float(raw)
            if timestamp <= 0:
                return None
            if timestamp > 100_000_000_000:
                timestamp /= 1000
            return datetime.fromtimestamp(timestamp, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None

    @staticmethod
    def _parse_pair(item: Any, chain: str, mint: str, now: datetime) -> PairSnapshot:
        if not isinstance(item, dict):
            raise MalformedData(SERVICE, "pair entry is not an object")
        if item.get("chainId") != chain:
            raise MalformedData(SERVICE, "pair belongs to another chain")
        base = item.get("baseToken")
        if not isinstance(base, dict) or base.get("address") != mint:
            raise MalformedData(SERVICE, "base token does not match requested mint")
        liquidity = item.get("liquidity") or {}
        volume = item.get("volume") or {}
        if not isinstance(liquidity, dict) or not isinstance(volume, dict):
            raise MalformedData(SERVICE, "liquidity or volume is not an object")
        try:
            return PairSnapshot.create(
                chain=chain,
                pair_address=require_str(
                    item.get("pairAddress"), service=SERVICE, field="pairAddress"
                ),
                dex_id=require_str(item.get("dexId"), service=SERVICE, field="dexId"),
                base_mint=mint,
                base_symbol=str(base.get("symbol") or "UNKNOWN")[:32],
                price_usd=to_decimal(
                    item.get("priceUsd"), service=SERVICE, field="priceUsd"
                ),
                liquidity_usd=to_decimal(
                    liquidity.get("usd", 0), service=SERVICE, field="liquidity.usd"
                ),
                volume_24h_usd=to_decimal(
                    volume.get("h24", 0), service=SERVICE, field="volume.h24"
                ),
                observed_at=now,
                pair_created_at=DexScreenerAdapter._pair_created_at(item),
                source="DexScreener",
            )
        except DomainError as exc:
            raise MalformedData(SERVICE, str(exc)) from None
