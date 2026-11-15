"""Jito read-only adapter: tip accounts (JSON-RPC getTipAccounts) and tip floor (REST).

Verified endpoints: POST https://mainnet.block-engine.jito.wtf/api/v1/bundles with JSON-RPC
method getTipAccounts (returns 8 accounts), and GET https://bundles.jito.wtf/api/v1/bundles/tip_floor.

There is NO submit method in this module. Bundle plans are built and checked locally. The
tip_floor field name and unit are unverified: this adapter reads `landed_tips_50th_percentile`
as SOL and converts to lamports, and refuses the response if the field is missing.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bangzen_prime.core import rust_bridge
from bangzen_prime.core.errors import DomainError
from bangzen_prime.data.http import (
    HttpRequest,
    RequestTransport,
    request_json,
)
from bangzen_prime.data.parsing import (
    MalformedData,
    to_decimal,
)
from bangzen_prime.data.retry.policies import ResilientCaller
from bangzen_prime.discovery.tokens import validate_mint
from bangzen_prime.execution.tip import dynamic_tip_lamports

BLOCK_ENGINE = "https://mainnet.block-engine.jito.wtf/api/v1/bundles"
TIP_FLOOR_URL = "https://bundles.jito.wtf/api/v1/bundles/tip_floor"
SERVICE = "jito"
LAMPORTS_PER_SOL = Decimal(1_000_000_000)
MAX_BUNDLE_TXS = 5


@dataclass(frozen=True)
class BundlePlan:
    """A local, unsigned description of a bundle. It is never submitted in this release."""

    tip_account: str
    tip_lamports: Decimal
    transaction_count: int


class JitoClient:
    def __init__(
        self,
        *,
        transport: RequestTransport,
        caller: ResilientCaller,
        timeout: float,
        clock: Callable[[], datetime],
        block_engine: str = BLOCK_ENGINE,
        tip_floor_url: str = TIP_FLOOR_URL,
    ) -> None:
        self._transport = transport
        self._caller = caller
        self._timeout = timeout
        self._clock = clock
        self._block_engine = block_engine
        self._tip_floor_url = tip_floor_url

    def tip_accounts(self) -> list[str]:
        body = json.dumps(
            {"jsonrpc": "2.0", "id": 1, "method": "getTipAccounts", "params": []}
        ).encode("utf-8")
        request = HttpRequest(
            "POST",
            self._block_engine,
            {"Content-Type": "application/json"},
            body,
            self._timeout,
        )
        payload = self._caller.call(
            lambda: request_json(
                service=SERVICE, request=request, transport=self._transport
            )
        )
        result = payload.get("result") if isinstance(payload, dict) else None
        if not isinstance(result, list) or not result:
            raise MalformedData(SERVICE, "tip accounts missing")
        accounts = []
        for item in result:
            if not isinstance(item, str):
                raise MalformedData(SERVICE, "tip account is not a string")
            validate_mint(item)  # same base58 shape check as token addresses
            accounts.append(item)
        return accounts

    def tip_floor_lamports(self) -> Decimal:
        request = HttpRequest(
            "GET",
            self._tip_floor_url,
            {"accept": "application/json"},
            None,
            self._timeout,
        )
        payload = self._caller.call(
            lambda: request_json(
                service=SERVICE, request=request, transport=self._transport
            )
        )
        entry = payload[0] if isinstance(payload, list) and payload else payload
        if not isinstance(entry, dict):
            raise MalformedData(SERVICE, "tip floor entry missing")
        sol = to_decimal(
            entry.get("landed_tips_50th_percentile"),
            service=SERVICE,
            field="landed_tips_50th_percentile",
        )
        return sol * LAMPORTS_PER_SOL

    def plan_bundle(
        self,
        *,
        transaction_count: int,
        expected_gain_lamports: Decimal,
        cap_lamports: int,
        tip_account: str,
    ) -> BundlePlan:
        """Price the tip and check bundle limits. Pure local computation. Sends nothing."""
        if not (1 <= transaction_count <= MAX_BUNDLE_TXS):
            raise DomainError("a bundle holds 1 to 5 transactions")
        validate_mint(tip_account)
        floor = self.tip_floor_lamports()
        tip = dynamic_tip_lamports(
            market_floor_lamports=floor,
            expected_gain_lamports=expected_gain_lamports,
            cap_lamports=cap_lamports,
        )
        if not rust_bridge.bundle_within_limits(
            transaction_count, int(tip), cap_lamports
        ):
            raise DomainError("bundle exceeds limits")
        return BundlePlan(tip_account, tip, transaction_count)
