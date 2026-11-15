"""Helius JSON-RPC adapter (read-only). Standard Solana RPC methods:
getTokenAccountsByOwner, getSignatureStatuses and getAccountInfo, at https://mainnet.helius-rpc.com/?api-key=...

Helius accepts the key in the query string, so the URL carries the key. Exception messages never
include the URL, so the key does not reach logs.

`simulate` and `send` are deliberately refused: they need a signed transaction, and signing is
not part of this release.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from bangzen_prime.application.ports import SimulationResult
from bangzen_prime.domain.tokens import validate_mint
from bangzen_prime.errors import DomainError, ExternalServiceError
from bangzen_prime.infrastructure.adapters.market_data.parsing import (
    MalformedData,
    to_decimal,
)
from bangzen_prime.infrastructure.http import (
    HttpRequest,
    RequestTransport,
    request_json,
)
from bangzen_prime.infrastructure.resilience.policies import ResilientCaller

SERVICE = "helius"


class BroadcastRefused(ExternalServiceError):
    pass


class HeliusRpc:
    def __init__(
        self,
        *,
        api_key: str,
        transport: RequestTransport,
        caller: ResilientCaller,
        timeout: float,
        clock: Callable[[], datetime],
        base_url: str = "https://mainnet.helius-rpc.com",
    ) -> None:
        if not api_key:
            raise DomainError("Helius API key is required")
        self._key = api_key
        self._transport = transport
        self._caller = caller
        self._timeout = timeout
        self._clock = clock
        self._base = base_url.rstrip("/")

    def _rpc(self, method: str, params: list[Any]) -> Any:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        ).encode()
        request = HttpRequest(
            "POST",
            f"{self._base}/?api-key={self._key}",
            {"Content-Type": "application/json"},
            body,
            self._timeout,
        )
        payload = self._caller.call(
            lambda: request_json(
                service=SERVICE, request=request, transport=self._transport
            )
        )
        if not isinstance(payload, dict):
            raise MalformedData(SERVICE, "expected a JSON-RPC object")
        if "error" in payload:
            raise ExternalServiceError(
                "rpc returned an error", service=SERVICE, retryable=False
            )
        return payload.get("result")

    def account_info(self, address: str) -> dict[str, Any]:
        """Fetch one account with base64 data and finalized commitment; read-only."""
        validate_mint(address)
        result = self._rpc(
            "getAccountInfo",
            [address, {"encoding": "base64", "commitment": "finalized"}],
        )
        if not isinstance(result, dict):
            raise MalformedData(SERVICE, "getAccountInfo result missing or malformed")
        return result

    def token_balance(self, owner: str, mint: str) -> Decimal:
        validate_mint(owner)
        validate_mint(mint)
        result = self._rpc(
            "getTokenAccountsByOwner",
            [owner, {"mint": mint}, {"encoding": "jsonParsed"}],
        )
        if not isinstance(result, dict) or not isinstance(result.get("value"), list):
            raise MalformedData(SERVICE, "token accounts missing")
        total = Decimal(0)
        for account in result["value"]:
            try:
                amount = account["account"]["data"]["parsed"]["info"]["tokenAmount"][
                    "uiAmountString"
                ]
            except (KeyError, TypeError):
                raise MalformedData(SERVICE, "token amount missing") from None
            total += to_decimal(amount, service=SERVICE, field="uiAmountString")
        return total

    def signature_status(self, signature: str) -> str:
        if not signature or len(signature) > 128:
            raise DomainError("invalid signature")
        result = self._rpc("getSignatureStatuses", [[signature]])
        value = result.get("value") if isinstance(result, dict) else None
        if not isinstance(value, list) or not value or value[0] is None:
            return "NOT_FOUND"
        if value[0].get("err") is not None:
            return "FAILED"
        level = value[0].get("confirmationStatus")
        return {
            "processed": "PROCESSED",
            "confirmed": "CONFIRMED",
            "finalized": "FINALIZED",
        }.get(level, "NOT_FOUND")

    def simulate(self, plan) -> SimulationResult:
        return SimulationResult(False, "NO_SIGNED_TRANSACTION")

    def send(self, signed) -> str:
        raise BroadcastRefused(
            "broadcast is disabled in this release", service=SERVICE, retryable=False
        )
