"""DexScreener adapter. Provides rich token snapshots for strategies."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from urllib.parse import quote

from bangzen_prime.domain.tokens import validate_chain, validate_mint
from bangzen_prime.infrastructure.http import Transport, get_json
from bangzen_prime.infrastructure.resilience.policies import ResilientCaller

logger = logging.getLogger("bangzen_prime.dexscreener")
SERVICE = "dexscreener"


def _f(value: Any) -> float:
    try:
        return float(value) if value is not None else 0.0
    except (TypeError, ValueError):
        return 0.0


def _i(value: Any) -> int:
    try:
        return int(value) if value is not None else 0
    except (TypeError, ValueError):
        return 0


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

    def fetch_rich_snapshot(self, chain: str, mint: str) -> Any | None:
        """Mengambil data pasar lengkap (volume, txns, umur) untuk strategi."""
        validate_chain(chain)
        validate_mint(mint)
        url = f"{self._base}/tokens/{quote(mint, safe='')}"

        try:
            data = self._caller.call(
                lambda: get_json(
                    service=SERVICE,
                    url=url,
                    timeout=self._timeout,
                    transport=self._transport,
                )
            )
        except Exception as e:
            logger.warning(f"DexScreener fetch failed for {mint[:8]}: {e}")
            return None

        pairs = data.get("pairs") if isinstance(data, dict) else None
        if not pairs:
            return None

        # Pilih pair dengan likuiditas tertinggi
        best = max(pairs, key=lambda p: _f((p.get("liquidity") or {}).get("usd")))
        return self._parse_rich_pair(mint, best)

    def _parse_rich_pair(self, mint: str, pair: dict[str, Any]) -> Any:
        now = self._clock()
        created_ms = pair.get("pairCreatedAt")
        created_at = None
        age_minutes = 0.0

        if created_ms:
            try:
                created_at = datetime.fromtimestamp(created_ms / 1000, tz=UTC)
                age_minutes = (now - created_at).total_seconds() / 60.0
            except (OverflowError, OSError, ValueError):
                pass

        volume = pair.get("volume") or {}
        txns = pair.get("txns") or {}
        txns_5m = txns.get("m5") or {}
        txns_1h = txns.get("h1") or {}
        price_change = pair.get("priceChange") or {}
        liquidity = pair.get("liquidity") or {}
        info = pair.get("info") or {}

        # Menggunakan SimpleNamespace sebagai "TokenSnapshot" agar tidak perlu ubah domain
        return SimpleNamespace(
            chain="solana",
            token_address=mint,
            symbol=(pair.get("baseToken") or {}).get("symbol", "???"),
            name=(pair.get("baseToken") or {}).get("name", "Unknown"),
            pair_address=pair.get("pairAddress"),
            dex_id=pair.get("dexId"),
            price_usd=_f(pair.get("priceUsd")),
            market_cap_usd=_f(pair.get("marketCap")),
            liquidity_usd=_f(liquidity.get("usd")),
            volume_5m_usd=_f(volume.get("m5")),
            volume_1h_usd=_f(volume.get("h1")),
            volume_24h_usd=_f(volume.get("h24")),
            txns_5m_buys=_i(txns_5m.get("buys")),
            txns_5m_sells=_i(txns_5m.get("sells")),
            txns_1h_buys=_i(txns_1h.get("buys")),
            txns_1h_sells=_i(txns_1h.get("sells")),
            price_change_5m_pct=_f(price_change.get("m5")),
            price_change_1h_pct=_f(price_change.get("h1")),
            price_change_24h_pct=_f(price_change.get("h24")),
            created_at=created_at,
            age_minutes=age_minutes,
        )
