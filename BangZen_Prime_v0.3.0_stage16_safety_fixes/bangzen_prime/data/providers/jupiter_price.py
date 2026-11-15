"""Read-only Jupiter Price API V3 adapter for slot-validated quote-currency prices.

Jupiter returns USD prices keyed by mint. This adapter requests both mints in one
response, validates each observation against an injected current Solana slot, and
derives target-token units per one quote-token unit using Decimal arithmetic.

Price API output is a reference/last-swap heuristic, not an executable fill price.
Use Jupiter Swap API quotes for amount-specific execution economics.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation, localcontext
from urllib.parse import quote

from bangzen_prime.core.errors import DomainError
from bangzen_prime.data.http import (
    HttpRequest,
    RequestTransport,
    request_json,
)
from bangzen_prime.data.retry.policies import ResilientCaller
from bangzen_prime.discovery.tokens import validate_mint
from bangzen_prime.execution.quote_economics import VerifiedQuotePrice

BASE_URL = "https://api.jup.ag/price/v3"
SERVICE = "jupiter_price_v3"


class JupiterPriceMalformed(Exception):
    """Provider response is structurally invalid and must not become evidence."""


@dataclass(frozen=True)
class JupiterPriceObservation:
    evidence: VerifiedQuotePrice
    target_usd_price: Decimal
    quote_usd_price: Decimal
    target_liquidity_usd: Decimal
    quote_liquidity_usd: Decimal
    target_block_slot: int
    quote_block_slot: int
    observed_at: datetime
    source_record_id: str


class JupiterPriceEvidenceAdapter:
    """Fetch and validate a two-mint USD price snapshot.

    max_slot_lag is an explicit policy input supplied by the composition root; this
    adapter does not silently choose a freshness threshold. No key is logged or
    included in exception messages. The API key is held only in the request header.
    """

    def __init__(
        self,
        *,
        api_key: str,
        transport: RequestTransport,
        caller: ResilientCaller,
        timeout: float,
        current_slot,
        clock,
        max_slot_lag: int,
        base_url: str = BASE_URL,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise DomainError("Jupiter API key is required")
        if (
            isinstance(timeout, bool)
            or not isinstance(timeout, (int, float))
            or timeout <= 0
        ):
            raise DomainError("timeout must be positive")
        if not callable(current_slot) or not callable(clock):
            raise DomainError("current_slot and clock callables are required")
        if (
            isinstance(max_slot_lag, bool)
            or not isinstance(max_slot_lag, int)
            or max_slot_lag < 0
        ):
            raise DomainError("max_slot_lag must be a non-negative integer")
        self._api_key = api_key.strip()
        self._transport = transport
        self._caller = caller
        self._timeout = float(timeout)
        self._current_slot = current_slot
        self._clock = clock
        self._max_slot_lag = max_slot_lag
        self._base = base_url.rstrip("/")

    def fetch_quote_price(
        self, *, mint: str, quote_mint: str
    ) -> JupiterPriceObservation:
        validate_mint(mint)
        validate_mint(quote_mint)
        if mint == quote_mint:
            raise DomainError(
                "price conversion mints must differ; same-mint uses identity"
            )
        # URL-encode only the comma separator and validated base58 addresses.
        ids = quote(mint, safe="") + "%2C" + quote(quote_mint, safe="")
        request = HttpRequest(
            "GET",
            f"{self._base}?ids={ids}",
            {"x-api-key": self._api_key, "Accept": "application/json"},
            None,
            self._timeout,
        )
        payload = self._caller.call(
            lambda: request_json(
                service=SERVICE, request=request, transport=self._transport
            )
        )
        now = self._clock()
        current = self._current_slot()
        if isinstance(current, bool) or not isinstance(current, int) or current < 0:
            raise DomainError("current Solana slot is invalid")
        if (
            not isinstance(now, datetime)
            or now.tzinfo is None
            or now.utcoffset() is None
        ):
            raise DomainError("clock must return a timezone-aware datetime")
        target = self._parse_price(payload, mint, current)
        quote_price = self._parse_price(payload, quote_mint, current)
        with localcontext() as context:
            context.prec = 50
            rate = target.usd_price / quote_price.usd_price
        source_id = f"{mint}:{target.block_slot}|{quote_mint}:{quote_price.block_slot}"
        evidence = VerifiedQuotePrice(
            mint=mint,
            quote_mint=quote_mint,
            quote_per_token=rate,
            source=SERVICE,
            observed_at=now,
            validation_status="VERIFIED",
            # Keep the target price's slot in the legacy domain DTO. Both exact
            # slots remain available on this adapter observation.
            slot=target.block_slot,
        )
        return JupiterPriceObservation(
            evidence=evidence,
            target_usd_price=target.usd_price,
            quote_usd_price=quote_price.usd_price,
            target_liquidity_usd=target.liquidity_usd,
            quote_liquidity_usd=quote_price.liquidity_usd,
            target_block_slot=target.block_slot,
            quote_block_slot=quote_price.block_slot,
            observed_at=now,
            source_record_id=source_id,
        )

    def _parse_price(self, payload: object, mint: str, current_slot: int):
        if not isinstance(payload, dict):
            raise JupiterPriceMalformed("price response must be a mint-keyed object")
        raw = payload.get(mint)
        if not isinstance(raw, dict):
            raise JupiterPriceMalformed("requested mint price is absent")
        usd_price = self._positive_decimal(raw.get("usdPrice"), "usdPrice")
        liquidity = self._positive_decimal(raw.get("liquidity"), "liquidity")
        slot = raw.get("blockId")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise JupiterPriceMalformed("blockId must be a non-negative integer")
        lag = current_slot - slot
        if lag < 0 or lag > self._max_slot_lag:
            raise JupiterPriceMalformed("price block is stale or ahead of current slot")
        # decimals is deliberately not used here; verified mint decimals come from
        # the finalized account reader (PR #45), not this price provider.
        return _ParsedPrice(usd_price, liquidity, slot)

    @staticmethod
    def _positive_decimal(value: object, field: str) -> Decimal:
        if isinstance(value, bool) or value is None:
            raise JupiterPriceMalformed(f"{field} is missing or invalid")
        try:
            result = Decimal(str(value))
        except (InvalidOperation, ValueError):
            raise JupiterPriceMalformed(f"{field} is invalid") from None
        if not result.is_finite() or result <= 0:
            raise JupiterPriceMalformed(f"{field} must be finite and positive")
        return result


@dataclass(frozen=True)
class _ParsedPrice:
    usd_price: Decimal
    liquidity_usd: Decimal
    block_slot: int
