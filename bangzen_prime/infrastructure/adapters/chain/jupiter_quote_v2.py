"""Read-only Jupiter Swap API V2 quote and fee metadata adapter.

Uses GET /order without a taker: no transaction is requested, built, signed, or submitted.
Amounts and fees remain in raw token units; callers must normalize decimals and quote-currency
conversion before passing costs into execution_economics.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from urllib.parse import urlencode

from bangzen_prime.domain.tokens import validate_mint
from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.adapters.market_data.parsing import (
    MalformedData,
    require_str,
    to_decimal,
)
from bangzen_prime.infrastructure.http import (
    HttpRequest,
    RequestTransport,
    request_json,
)
from bangzen_prime.infrastructure.resilience.policies import ResilientCaller

JUPITER_V2_BASE = "https://api.jup.ag/swap/v2"
SERVICE = "jupiter_v2_quote"
ALLOWED_ROUTERS = frozenset({"metis", "jupiterz", "dflow", "okx"})


@dataclass(frozen=True)
class JupiterPlatformFee:
    amount_raw: Decimal
    fee_bps: int
    fee_mint: str


@dataclass(frozen=True)
class JupiterQuoteV2:
    request_id: str
    input_mint: str
    output_mint: str
    input_amount_raw: Decimal
    output_amount_raw: Decimal
    router: str
    mode: str | None
    total_fee_bps: int
    fee_mint: str
    platform_fee: JupiterPlatformFee | None


class JupiterQuoteV2Adapter:
    """Fetch quote-only /order data; never requests an assembled transaction."""

    def __init__(
        self,
        *,
        api_key: str,
        transport: RequestTransport,
        caller: ResilientCaller,
        timeout: float,
        base_url: str = JUPITER_V2_BASE,
    ) -> None:
        if not isinstance(api_key, str) or not api_key.strip():
            raise DomainError("Jupiter API key is required")
        if timeout <= 0:
            raise DomainError("timeout must be positive")
        self._api_key = api_key
        self._transport = transport
        self._caller = caller
        self._timeout = timeout
        self._base = base_url.rstrip("/")

    def quote(
        self, *, input_mint: str, output_mint: str, amount: int
    ) -> JupiterQuoteV2:
        validate_mint(input_mint)
        validate_mint(output_mint)
        if input_mint == output_mint:
            raise DomainError("input and output mint must differ")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise DomainError("amount must be a positive integer in raw token units")

        query = urlencode(
            {
                "inputMint": input_mint,
                "outputMint": output_mint,
                "amount": str(amount),
            }
        )
        request = HttpRequest(
            "GET",
            f"{self._base}/order?{query}",
            {"x-api-key": self._api_key, "accept": "application/json"},
            None,
            self._timeout,
        )
        payload = self._caller.call(
            lambda: request_json(
                service=SERVICE, request=request, transport=self._transport
            )
        )
        return self._parse(payload, input_mint, output_mint, amount)

    @staticmethod
    def _parse(
        payload: object, input_mint: str, output_mint: str, requested_amount: int
    ) -> JupiterQuoteV2:
        if not isinstance(payload, dict):
            raise MalformedData(SERVICE, "order response must be an object")
        # Quote-only contract: a non-null transaction means the request unexpectedly
        # crossed into transaction construction and must not be consumed by this adapter.
        if payload.get("transaction") not in (None, ""):
            raise MalformedData(
                SERVICE, "quote-only response unexpectedly contains a transaction"
            )

        request_id = require_str(
            payload.get("requestId"), service=SERVICE, field="requestId"
        )
        if len(request_id) > 256:
            raise MalformedData(SERVICE, "requestId is too long")
        if (
            require_str(payload.get("inputMint"), service=SERVICE, field="inputMint")
            != input_mint
        ):
            raise MalformedData(SERVICE, "quote input mint mismatch")
        if (
            require_str(payload.get("outputMint"), service=SERVICE, field="outputMint")
            != output_mint
        ):
            raise MalformedData(SERVICE, "quote output mint mismatch")

        input_raw = to_decimal(
            payload.get("inAmount"), service=SERVICE, field="inAmount"
        )
        output_raw = to_decimal(
            payload.get("outAmount"), service=SERVICE, field="outAmount"
        )
        if input_raw != Decimal(requested_amount) or output_raw <= 0:
            raise MalformedData(
                SERVICE, "quote amounts are invalid or do not match request"
            )

        router = require_str(
            payload.get("router"), service=SERVICE, field="router"
        ).lower()
        if router not in ALLOWED_ROUTERS:
            raise MalformedData(SERVICE, "unsupported router")
        mode_value = payload.get("mode")
        if mode_value is not None and mode_value not in ("ultra", "manual"):
            raise MalformedData(SERVICE, "unsupported order mode")

        fee_bps = payload.get("feeBps")
        if (
            isinstance(fee_bps, bool)
            or not isinstance(fee_bps, int)
            or not 0 <= fee_bps <= 10_000
        ):
            raise MalformedData(SERVICE, "feeBps must be an integer within [0, 10000]")
        fee_mint = require_str(payload.get("feeMint"), service=SERVICE, field="feeMint")
        try:
            validate_mint(fee_mint)
        except DomainError:
            raise MalformedData(SERVICE, "feeMint is not a valid mint") from None

        platform_fee = None
        platform_payload = payload.get("platformFee")
        if platform_payload is not None:
            if not isinstance(platform_payload, dict):
                raise MalformedData(SERVICE, "platformFee must be an object")
            fee_amount = to_decimal(
                platform_payload.get("amount"),
                service=SERVICE,
                field="platformFee.amount",
            )
            platform_bps = platform_payload.get("feeBps")
            if (
                isinstance(platform_bps, bool)
                or not isinstance(platform_bps, int)
                or not 0 <= platform_bps <= 10_000
                or fee_amount < 0
            ):
                raise MalformedData(SERVICE, "platform fee amount or bps is invalid")
            platform_fee = JupiterPlatformFee(fee_amount, platform_bps, fee_mint)

        return JupiterQuoteV2(
            request_id=request_id,
            input_mint=input_mint,
            output_mint=output_mint,
            input_amount_raw=input_raw,
            output_amount_raw=output_raw,
            router=router,
            mode=mode_value,
            total_fee_bps=fee_bps,
            fee_mint=fee_mint,
            platform_fee=platform_fee,
        )
