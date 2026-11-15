"""DexScreener adapter for validated Solana market-pair snapshots."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from math import isfinite
from typing import Any
from urllib.parse import quote

from bangzen_prime.domain.tokens import PairSnapshot, validate_chain, validate_mint
from bangzen_prime.errors import DomainError, ExternalServiceError
from bangzen_prime.infrastructure.http import Transport, get_json
from bangzen_prime.infrastructure.resilience.policies import ResilientCaller

SERVICE = "dexscreener"


class DexScreenerAdapter:
    """Fetch and normalize valid DEX pairs for one Solana mint."""

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

        url = (
            f"{self._base}/token-pairs/v1/"
            f"{quote(chain, safe='')}/{quote(mint, safe='')}"
        )
        payload = self._caller.call(
            lambda: get_json(
                service=SERVICE,
                url=url,
                timeout=self._timeout,
                transport=self._transport,
            )
        )

        if not isinstance(payload, list):
            raise ExternalServiceError(
                "DexScreener returned an unexpected pair payload",
                service=SERVICE,
                retryable=False,
            )

        observed_at = self._clock()
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise DomainError("DexScreener clock must be timezone-aware")

        snapshots: list[PairSnapshot] = []

        for raw in payload:
            if not isinstance(raw, dict):
                continue
            if raw.get("chainId") != chain:
                continue

            base = raw.get("baseToken")
            if not isinstance(base, dict) or base.get("address") != mint:
                continue

            try:
                pair_address = self._required_text(raw.get("pairAddress"))
                dex_id = self._required_text(raw.get("dexId"))
                symbol = self._required_text(base.get("symbol"))

                liquidity_data = raw.get("liquidity")
                volume_data = raw.get("volume")
                if not isinstance(liquidity_data, dict):
                    continue
                if not isinstance(volume_data, dict):
                    continue

                price = self._decimal(raw.get("priceUsd"))
                liquidity = self._decimal(liquidity_data.get("usd"))
                volume = self._decimal(volume_data.get("h24"))

                if price <= 0 or liquidity < 0 or volume < 0:
                    continue

                snapshots.append(
                    PairSnapshot.create(
                        chain=chain,
                        pair_address=pair_address,
                        dex_id=dex_id,
                        base_mint=mint,
                        base_symbol=symbol,
                        price_usd=price,
                        liquidity_usd=liquidity,
                        volume_24h_usd=volume,
                        observed_at=observed_at,
                        pair_created_at=self._created_at(
                            raw.get("pairCreatedAt")
                        ),
                        source=SERVICE,
                    )
                )
            except (
                DomainError,
                InvalidOperation,
                TypeError,
                ValueError,
                OverflowError,
            ):
                # Skip one invalid pair without discarding other valid pairs.
                continue

        return snapshots

    @staticmethod
    def _required_text(value: Any) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("required text field is missing")
        return value.strip()

    @staticmethod
    def _decimal(value: Any) -> Decimal:
        if value is None or isinstance(value, bool):
            raise InvalidOperation("missing or invalid decimal")
        try:
            result = Decimal(str(value).strip())
        except (InvalidOperation, ValueError, AttributeError):
            raise InvalidOperation("invalid decimal") from None
        if not result.is_finite():
            raise InvalidOperation("non-finite decimal")
        return result

    @staticmethod
    def _created_at(value: Any) -> datetime | None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if isinstance(value, float) and not isfinite(value):
            return None
        try:
            return datetime.fromtimestamp(value / 1000, tz=UTC)
        except (OverflowError, OSError, ValueError):
            return None
