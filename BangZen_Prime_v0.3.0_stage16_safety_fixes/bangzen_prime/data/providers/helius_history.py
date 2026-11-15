"""Validated, read-only Helius historical RPC evidence.

History pages are provider observations, not proof of complete chain coverage.
The caller must retain pagination cursors and must not label partial pages VERIFIED.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bangzen_prime.core.errors import DomainError, ExternalServiceError
from bangzen_prime.data.http import (
    HttpRequest,
    RequestTransport,
    request_json,
)
from bangzen_prime.data.retry.policies import ResilientCaller

SERVICE = "helius"
_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_SIGNATURE_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{64,88}$")
_MAX_PAGE_SIZE = 1000


class HeliusHistoryMalformed(ExternalServiceError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            f"helius historical response malformed: {detail}",
            service=SERVICE,
            retryable=False,
        )


@dataclass(frozen=True)
class HistoricalSignature:
    signature: str
    slot: int
    block_time: int | None
    transaction_error: bool
    confirmation_status: str | None
    memo: str | None


@dataclass(frozen=True)
class HistoricalSignaturePage:
    address: str
    entries: tuple[HistoricalSignature, ...]
    requested_limit: int
    before_signature: str | None
    until_signature: str | None
    next_before_signature: str | None
    exhausted: bool
    observed_at: datetime
    source: str = "helius_getSignaturesForAddress"


@dataclass(frozen=True)
class HistoricalTransaction:
    signature: str
    slot: int
    block_time: int | None
    fee_lamports: int | None
    account_keys: tuple[str, ...]
    pre_balances: tuple[int, ...]
    post_balances: tuple[int, ...]
    transaction_error: bool
    metadata_available: bool
    source: str = "helius_getTransaction"


class HeliusHistoryReader:
    """Bounded Helius HTTP history reader using the project's retry/budget caller."""

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
        if timeout <= 0:
            raise DomainError("Helius history timeout must be positive")
        if not base_url.startswith("https://") or "?" in base_url:
            raise DomainError("Helius history endpoint must be a clean HTTPS URL")
        self._key = api_key
        self._transport = transport
        self._caller = caller
        self._timeout = timeout
        self._clock = clock
        self._base = base_url.rstrip("/")

    def _rpc(self, method: str, params: list[Any]) -> Any:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            separators=(",", ":"),
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
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            raise HeliusHistoryMalformed("expected JSON-RPC 2.0 object")
        if payload.get("error") is not None:
            raise ExternalServiceError(
                "helius historical RPC returned an error",
                service=SERVICE,
                retryable=False,
            )
        if "result" not in payload:
            raise HeliusHistoryMalformed("result field missing")
        return payload["result"]

    @staticmethod
    def _decode_base58(value: str) -> bytes:
        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        number = 0
        for char in value:
            digit = alphabet.find(char)
            if digit < 0:
                raise ValueError("invalid base58")
            number = number * 58 + digit
        decoded = (
            number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
        )
        leading_zeroes = len(value) - len(value.lstrip("1"))
        return (b"\x00" * leading_zeroes) + decoded

    @classmethod
    def _validate_address(cls, address: str) -> None:
        if not isinstance(address, str) or not _ADDRESS_RE.fullmatch(address):
            raise DomainError("invalid Solana address")
        try:
            valid_length = len(cls._decode_base58(address)) == 32
        except ValueError:
            valid_length = False
        if not valid_length:
            raise DomainError("invalid Solana address")

    @classmethod
    def _validate_signature(cls, signature: str | None, field: str) -> None:
        if signature is None:
            return
        if not isinstance(signature, str) or not _SIGNATURE_RE.fullmatch(signature):
            raise DomainError(f"invalid {field} signature")
        try:
            valid_length = len(cls._decode_base58(signature)) == 64
        except ValueError:
            valid_length = False
        if not valid_length:
            raise DomainError(f"invalid {field} signature")

    def signatures_for_address(
        self,
        address: str,
        *,
        limit: int = 100,
        before: str | None = None,
        until: str | None = None,
    ) -> HistoricalSignaturePage:
        self._validate_address(address)
        if (
            isinstance(limit, bool)
            or not isinstance(limit, int)
            or not 1 <= limit <= _MAX_PAGE_SIZE
        ):
            raise DomainError("history page limit must be between 1 and 1000")
        self._validate_signature(before, "before")
        self._validate_signature(until, "until")
        options: dict[str, Any] = {"limit": limit}
        if before is not None:
            options["before"] = before
        if until is not None:
            options["until"] = until

        result = self._rpc("getSignaturesForAddress", [address, options])
        if not isinstance(result, list) or len(result) > limit:
            raise HeliusHistoryMalformed("signature page must be a bounded array")

        entries: list[HistoricalSignature] = []
        seen: set[str] = set()
        previous_slot: int | None = None
        for item in result:
            if not isinstance(item, dict):
                raise HeliusHistoryMalformed("signature entry must be an object")
            signature = item.get("signature")
            slot = item.get("slot")
            block_time = item.get("blockTime")
            confirmation = item.get("confirmationStatus")
            memo = item.get("memo")
            try:
                self._validate_signature(signature, "returned")
            except DomainError:
                raise HeliusHistoryMalformed("invalid signature") from None
            if signature in seen:
                raise HeliusHistoryMalformed("duplicate signature in provider page")
            seen.add(signature)
            if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
                raise HeliusHistoryMalformed("invalid slot")
            if previous_slot is not None and slot > previous_slot:
                raise HeliusHistoryMalformed("signature page is not newest-first")
            previous_slot = slot
            if block_time is not None and (
                isinstance(block_time, bool)
                or not isinstance(block_time, int)
                or block_time < 0
            ):
                raise HeliusHistoryMalformed("invalid blockTime")
            if confirmation is not None and confirmation not in {
                "processed",
                "confirmed",
                "finalized",
            }:
                raise HeliusHistoryMalformed("invalid confirmationStatus")
            if memo is not None and not isinstance(memo, str):
                raise HeliusHistoryMalformed("invalid memo")
            entries.append(
                HistoricalSignature(
                    signature=signature,
                    slot=slot,
                    block_time=block_time,
                    transaction_error=item.get("err") is not None,
                    confirmation_status=confirmation,
                    memo=memo,
                )
            )

        # Solana returns newest-first. Never infer completion from an exact full page.
        next_cursor = entries[-1].signature if entries else before
        if before is not None and next_cursor == before and entries:
            raise HeliusHistoryMalformed("pagination cursor did not advance")
        return HistoricalSignaturePage(
            address=address,
            entries=tuple(entries),
            requested_limit=limit,
            before_signature=before,
            until_signature=until,
            next_before_signature=next_cursor,
            exhausted=len(entries) < limit,
            observed_at=self._clock(),
        )

    def transaction(self, signature: str) -> HistoricalTransaction:
        self._validate_signature(signature, "transaction")
        result = self._rpc(
            "getTransaction",
            [
                signature,
                {
                    "encoding": "jsonParsed",
                    "commitment": "finalized",
                    "maxSupportedTransactionVersion": 0,
                },
            ],
        )
        if result is None:
            raise ExternalServiceError(
                "helius historical transaction is not available",
                service=SERVICE,
                retryable=False,
            )
        if not isinstance(result, dict):
            raise HeliusHistoryMalformed("transaction result must be an object")
        slot = result.get("slot")
        block_time = result.get("blockTime")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise HeliusHistoryMalformed("transaction slot missing or invalid")
        if block_time is not None and (
            isinstance(block_time, bool)
            or not isinstance(block_time, int)
            or block_time < 0
        ):
            raise HeliusHistoryMalformed("transaction blockTime invalid")
        meta = result.get("meta")
        if meta is None:
            return HistoricalTransaction(
                signature, slot, block_time, None, (), (), (), False, False
            )
        if not isinstance(meta, dict):
            raise HeliusHistoryMalformed("transaction meta must be an object")
        fee = meta.get("fee")
        if isinstance(fee, bool) or not isinstance(fee, int) or fee < 0:
            raise HeliusHistoryMalformed("transaction fee missing or invalid")
        transaction = result.get("transaction")
        if not isinstance(transaction, dict):
            raise HeliusHistoryMalformed("transaction object missing")
        message = transaction.get("message")
        if not isinstance(message, dict):
            raise HeliusHistoryMalformed("transaction message missing")
        keys = message.get("accountKeys")
        pre = meta.get("preBalances")
        post = meta.get("postBalances")
        if (
            not isinstance(keys, list)
            or not isinstance(pre, list)
            or not isinstance(post, list)
        ):
            raise HeliusHistoryMalformed("transaction account/balance arrays missing")
        if len(keys) != len(pre) or len(keys) != len(post):
            raise HeliusHistoryMalformed("account and balance array lengths disagree")

        account_keys: list[str] = []
        for key in keys:
            address = key.get("pubkey") if isinstance(key, dict) else key
            try:
                self._validate_address(address)
            except DomainError:
                raise HeliusHistoryMalformed(
                    "invalid transaction account key"
                ) from None
            account_keys.append(address)
        for balances in (pre, post):
            if any(
                isinstance(value, bool) or not isinstance(value, int) or value < 0
                for value in balances
            ):
                raise HeliusHistoryMalformed("invalid lamport balance")
        return HistoricalTransaction(
            signature=signature,
            slot=slot,
            block_time=block_time,
            fee_lamports=fee,
            account_keys=tuple(account_keys),
            pre_balances=tuple(pre),
            post_balances=tuple(post),
            transaction_error=meta.get("err") is not None,
            metadata_available=True,
        )
