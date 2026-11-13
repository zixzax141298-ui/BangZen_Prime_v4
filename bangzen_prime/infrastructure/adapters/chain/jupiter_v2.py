"""Jupiter Swap API V2 Meta-Aggregator adapter.

This adapter obtains an unsigned /order transaction and submits a caller-signed transaction
through /execute. It deliberately does not load keys or sign. The caller must enforce policy,
persist an idempotency record, validate the returned transaction, and own reconciliation.
"""
from __future__ import annotations

import base64
import binascii
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from urllib.parse import urlencode

from bangzen_prime.domain.tokens import validate_mint
from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.adapters.market_data.parsing import (
    MalformedData, require_str, to_decimal,
)
from bangzen_prime.infrastructure.http import HttpRequest, RequestTransport, request_json
from bangzen_prime.infrastructure.resilience.policies import ResilientCaller

JUPITER_V2_BASE = "https://api.jup.ag/swap/v2"
SERVICE = "jupiter_v2"
MAX_SOLANA_TRANSACTION_BYTES = 1232


@dataclass(frozen=True)
class JupiterOrder:
    request_id: str
    transaction_b64: str
    input_mint: str
    output_mint: str
    input_amount: Decimal
    output_amount: Decimal
    router: str
    transaction_version: int
    last_valid_block_height: int | None
    expire_at: str | None


@dataclass(frozen=True)
class JupiterExecution:
    status: str
    signature: str | None
    code: int
    total_input_amount: Decimal
    total_output_amount: Decimal


class JupiterSwapV2Adapter:
    def __init__(
        self, *, api_key: str, transport: RequestTransport, caller: ResilientCaller,
        timeout: float, base_url: str = JUPITER_V2_BASE,
    ) -> None:
        if not api_key or not api_key.strip():
            raise DomainError("Jupiter API key is required")
        if timeout <= 0:
            raise DomainError("timeout must be positive")
        self._api_key = api_key
        self._transport = transport
        self._caller = caller
        self._timeout = timeout
        self._base = base_url.rstrip("/")

    def order(self, *, input_mint: str, output_mint: str, amount: int, taker: str) -> JupiterOrder:
        validate_mint(input_mint)
        validate_mint(output_mint)
        validate_mint(taker)
        if input_mint == output_mint:
            raise DomainError("input and output mint must differ")
        if isinstance(amount, bool) or not isinstance(amount, int) or amount <= 0:
            raise DomainError("amount must be a positive integer in raw token units")
        query = urlencode({
            "inputMint": input_mint, "outputMint": output_mint,
            "amount": str(amount), "taker": taker, "maxSupportedTransactionVersion": "0",
        })
        request = HttpRequest(
            "GET", f"{self._base}/order?{query}",
            {"x-api-key": self._api_key, "accept": "application/json"}, None, self._timeout,
        )
        payload = self._caller.call(
            lambda: request_json(service=SERVICE, request=request, transport=self._transport)
        )
        if not isinstance(payload, dict):
            raise MalformedData(SERVICE, "order response must be an object")
        transaction = require_str(payload.get("transaction"), service=SERVICE, field="transaction")
        request_id = require_str(payload.get("requestId"), service=SERVICE, field="requestId")
        router = require_str(payload.get("router"), service=SERVICE, field="router")
        if len(request_id) > 256:
            raise MalformedData(SERVICE, "requestId is too long")
        try:
            raw_tx = base64.b64decode(transaction, validate=True)
        except (binascii.Error, ValueError):
            raise MalformedData(SERVICE, "transaction is not valid base64") from None
        if not raw_tx or len(raw_tx) > MAX_SOLANA_TRANSACTION_BYTES:
            raise MalformedData(SERVICE, "transaction size is outside Solana packet limits")
        version = payload.get("transactionVersion", 0)
        if isinstance(version, bool) or version not in (0,):
            raise MalformedData(SERVICE, "only explicitly supported transaction version 0 is accepted")
        in_amount = to_decimal(payload.get("inAmount"), service=SERVICE, field="inAmount")
        out_amount = to_decimal(payload.get("outAmount"), service=SERVICE, field="outAmount")
        if in_amount != Decimal(amount) or out_amount <= 0:
            raise MalformedData(SERVICE, "order amounts do not match the requested swap")
        if payload.get("inputMint") != input_mint or payload.get("outputMint") != output_mint:
            raise MalformedData(SERVICE, "order mints do not match the requested swap")
        last_valid = payload.get("lastValidBlockHeight")
        expire_at = payload.get("expireAt")
        if router == "jupiterz":
            if not isinstance(expire_at, str) or not expire_at.strip():
                raise MalformedData(SERVICE, "RFQ order is missing expireAt")
            try:
                expiry = datetime.fromisoformat(expire_at.replace("Z", "+00:00"))
            except ValueError:
                raise MalformedData(SERVICE, "RFQ expireAt is invalid") from None
            if expiry.tzinfo is None:
                raise MalformedData(SERVICE, "RFQ expireAt must include a timezone")
            last_valid = None
        else:
            if isinstance(last_valid, bool) or not isinstance(last_valid, int) or last_valid <= 0:
                raise MalformedData(SERVICE, "aggregator order is missing lastValidBlockHeight")
            expire_at = None
        return JupiterOrder(
            request_id=request_id, transaction_b64=transaction,
            input_mint=input_mint, output_mint=output_mint,
            input_amount=in_amount, output_amount=out_amount,
            router=router, transaction_version=version,
            last_valid_block_height=last_valid, expire_at=expire_at,
        )

    def execute(self, *, signed_transaction_b64: str, request_id: str) -> JupiterExecution:
        """Submit once only. Do not automatically retry: a timeout can have an unknown outcome."""
        if not isinstance(request_id, str) or not request_id.strip() or len(request_id) > 256:
            raise DomainError("a valid Jupiter request_id is required")
        if not isinstance(signed_transaction_b64, str) or not signed_transaction_b64:
            raise DomainError("signed transaction is required")
        try:
            raw_tx = base64.b64decode(signed_transaction_b64, validate=True)
        except (binascii.Error, ValueError):
            raise DomainError("signed transaction must be valid base64") from None
        if not raw_tx or len(raw_tx) > MAX_SOLANA_TRANSACTION_BYTES:
            raise DomainError("signed transaction size is outside Solana packet limits")
        body = json.dumps({
            "signedTransaction": signed_transaction_b64,
            "requestId": request_id,
        }, separators=(",", ":")).encode("utf-8")
        request = HttpRequest(
            "POST", f"{self._base}/execute",
            {"x-api-key": self._api_key, "Content-Type": "application/json"},
            body, self._timeout,
        )
        # No retry wrapper on a side-effecting request. Caller must reconcile unknown outcomes.
        payload = request_json(service=SERVICE, request=request, transport=self._transport)
        if not isinstance(payload, dict):
            raise MalformedData(SERVICE, "execute response must be an object")
        status = payload.get("status")
        code = payload.get("code")
        if status not in ("Success", "Failed") or isinstance(code, bool) or not isinstance(code, int):
            raise MalformedData(SERVICE, "execute status or code is invalid")
        signature = payload.get("signature")
        if signature is not None and (not isinstance(signature, str) or not signature.strip()):
            raise MalformedData(SERVICE, "signature is invalid")
        total_in = to_decimal(payload.get("totalInputAmount", "0"), service=SERVICE,
                              field="totalInputAmount")
        total_out = to_decimal(payload.get("totalOutputAmount", "0"), service=SERVICE,
                               field="totalOutputAmount")
        if total_in < 0 or total_out < 0:
            raise MalformedData(SERVICE, "execute amounts cannot be negative")
        if status == "Success" and (code != 0 or signature is None or total_in <= 0 or total_out <= 0):
            raise MalformedData(SERVICE, "success response is missing confirmed transaction fields")
        return JupiterExecution(status, signature, code, total_in, total_out)
