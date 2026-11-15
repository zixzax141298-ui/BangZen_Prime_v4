"""Jupiter swap quote adapter. Verified endpoint: GET https://api.jup.ag/swap/v2/quote with
inputMint, outputMint, amount, slippageBps, and an x-api-key header.

Quote-only. This adapter never builds, signs, or submits a swap transaction.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from bangzen_prime.core.errors import DomainError
from bangzen_prime.data.http import (
    HttpRequest,
    RequestTransport,
    request_json,
)
from bangzen_prime.data.parsing import (
    MalformedData,
    require_str,
    to_decimal,
)
from bangzen_prime.data.retry.policies import ResilientCaller
from bangzen_prime.discovery.tokens import validate_mint
from bangzen_prime.execution.execution import Quote

# Diubah ke V2
JUPITER_BASE = "https://api.jup.ag/swap/v2"
SERVICE = "jupiter"


class JupiterQuoteAdapter:
    def __init__(
        self,
        *,
        api_key: str,
        transport: RequestTransport,
        caller: ResilientCaller,
        timeout: float,
        clock: Callable[[], datetime],
        slippage_bps: int = 50,
        quote_ttl: timedelta = timedelta(seconds=20),
        base_url: str = JUPITER_BASE,
        provider: str = "jupiter-compatible",
    ) -> None:
        if not api_key:
            raise DomainError("Jupiter API key is required")
        if not (0 <= slippage_bps <= 1000):
            raise DomainError("slippage_bps must be within [0, 1000]")
        self._key = api_key
        self._transport = transport
        self._caller = caller
        self._timeout = timeout
        self._clock = clock
        self._slippage = slippage_bps
        self._ttl = quote_ttl
        self._base = base_url.rstrip("/")
        self._provider = provider

    def quote(self, input_mint: str, output_mint: str, in_amount: Decimal) -> Quote:
        validate_mint(input_mint)
        validate_mint(output_mint)
        if in_amount <= 0 or in_amount != in_amount.to_integral_value():
            raise DomainError("in_amount must be a positive whole number of raw units")

        # Menghapus &swapMode=ExactIn karena V2 default-nya sudah ExactIn
        url = (
            f"{self._base}/quote?inputMint={quote(input_mint, safe='')}&outputMint={quote(output_mint, safe='')}"
            f"&amount={int(in_amount)}&slippageBps={self._slippage}"
        )

        request = HttpRequest(
            "GET",
            url,
            {"x-api-key": self._key, "accept": "application/json"},
            None,
            self._timeout,
        )
        payload = self._caller.call(
            lambda: request_json(
                service=SERVICE, request=request, transport=self._transport
            )
        )
        return self._parse(payload, input_mint, output_mint, in_amount)

    def _parse(
        self, payload: Any, input_mint: str, output_mint: str, in_amount: Decimal
    ) -> Quote:
        if not isinstance(payload, dict):
            raise MalformedData(SERVICE, "expected an object")
        if (
            require_str(payload.get("inputMint"), service=SERVICE, field="inputMint")
            != input_mint
        ):
            raise MalformedData(SERVICE, "quote refers to another input mint")
        if (
            require_str(payload.get("outputMint"), service=SERVICE, field="outputMint")
            != output_mint
        ):
            raise MalformedData(SERVICE, "quote refers to another output mint")
        out_raw = to_decimal(
            payload.get("outAmount"), service=SERVICE, field="outAmount"
        )
        impact = to_decimal(
            payload.get("priceImpactPct", 0), service=SERVICE, field="priceImpactPct"
        )
        now = self._clock()
        try:
            return Quote.create(
                provider=self._provider,
                input_mint=input_mint,
                output_mint=output_mint,
                in_amount=in_amount,
                out_amount=out_raw,
                price_impact_pct=abs(impact),
                quoted_at=now,
                expires_at=now + self._ttl,
            )
        except DomainError as exc:
            raise MalformedData(SERVICE, str(exc)) from None

    async def check_dynamic_tax(self, mint: str) -> bool:
        """Fail-closed: dynamic tax / honeypot probe is not implemented on this quote adapter.

        HoneypotAdapter treats exceptions as UNAVAILABLE, which is the safe outcome.
        """
        validate_mint(mint)
        raise NotImplementedError(
            "JupiterQuoteAdapter does not implement dynamic-tax honeypot probing"
        )
