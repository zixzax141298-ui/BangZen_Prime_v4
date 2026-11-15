"""Birdeye and Solana Tracker market-intel adapters.

Verified against public docs: Birdeye base https://public-api.birdeye.so, GET /defi/token_overview
with X-API-KEY and x-chain headers. Solana Tracker base https://data.solanatracker.io, GET
/tokens/{mint} and /tokens/{mint}/holders with x-api-key header.

Field names beyond those shown in the docs are NOT verified. Every parser rejects a response
whose required fields are missing or non-numeric (fail closed).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass
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
    to_decimal,
)
from bangzen_prime.data.retry.policies import ResilientCaller
from bangzen_prime.discovery.tokens import validate_chain, validate_mint

BIRDEYE_BASE = "https://public-api.birdeye.so"
SOLANA_TRACKER_BASE = "https://data.solanatracker.io"


@dataclass(frozen=True)
class TokenIntel:
    mint: str
    symbol: str
    liquidity_usd: Decimal
    volume_24h_usd: Decimal
    price_usd: Decimal
    source: str
    observed_at: datetime


@dataclass(frozen=True)
class HolderProfile:
    mint: str
    holder_count: int
    top_holder_share_pct: Decimal | None
    source: str
    top_holders: tuple[str, ...] = ()


def _data(payload: Any, service: str) -> dict:
    if not isinstance(payload, dict):
        raise MalformedData(service, "expected an object")
    inner = payload.get("data", payload)
    if not isinstance(inner, dict):
        raise MalformedData(service, "data is not an object")
    return inner


class BirdeyeAdapter:
    SERVICE = "birdeye"

    def __init__(
        self,
        *,
        api_key: str,
        transport: RequestTransport,
        caller: ResilientCaller,
        timeout: float,
        clock: Callable[[], datetime],
        base_url: str = BIRDEYE_BASE,
    ) -> None:
        if not api_key:
            raise DomainError("Birdeye API key is required")
        self._key = api_key
        self._transport = transport
        self._caller = caller
        self._timeout = timeout
        self._clock = clock
        self._base = base_url.rstrip("/")

    def token_intel(self, chain: str, mint: str) -> TokenIntel:
        validate_chain(chain)
        validate_mint(mint)
        request = HttpRequest(
            "GET",
            f"{self._base}/defi/token_overview?address={quote(mint, safe='')}",
            {"X-API-KEY": self._key, "x-chain": chain, "accept": "application/json"},
            None,
            self._timeout,
        )
        payload = self._caller.call(
            lambda: request_json(
                service=self.SERVICE, request=request, transport=self._transport
            )
        )
        data = _data(payload, self.SERVICE)
        symbol = str(data.get("symbol") or "UNKNOWN")[:32]
        return TokenIntel(
            mint=mint,
            symbol=symbol,
            liquidity_usd=to_decimal(
                data.get("liquidity"), service=self.SERVICE, field="liquidity"
            ),
            volume_24h_usd=to_decimal(
                data.get("v24hUSD"), service=self.SERVICE, field="v24hUSD"
            ),
            price_usd=to_decimal(
                data.get("price"), service=self.SERVICE, field="price"
            ),
            source=self.SERVICE,
            observed_at=self._clock(),
        )


class SolanaTrackerAdapter:
    SERVICE = "solana_tracker"

    def __init__(
        self,
        *,
        api_key: str,
        transport: RequestTransport,
        caller: ResilientCaller,
        timeout: float,
        clock: Callable[[], datetime],
        base_url: str = SOLANA_TRACKER_BASE,
        cache_ttl_seconds: int = 300,
    ) -> None:
        if not api_key:
            raise DomainError("Solana Tracker API key is required")
        self._key = api_key
        self._transport = transport
        self._caller = caller
        self._timeout = timeout
        self._clock = clock
        self._base = base_url.rstrip("/")
        if not 1 <= cache_ttl_seconds <= 3600:
            raise ValueError("cache_ttl_seconds must be within [1, 3600]")
        self._holder_cache_ttl = timedelta(seconds=cache_ttl_seconds)
        self._holder_cache: dict[str, tuple[datetime, HolderProfile]] = {}
        self._cache_lock = threading.Lock()

    def _get(self, path: str) -> Any:
        request = HttpRequest(
            "GET",
            f"{self._base}{path}",
            {"x-api-key": self._key, "accept": "application/json"},
            None,
            self._timeout,
        )
        return self._caller.call(
            lambda: request_json(
                service=self.SERVICE, request=request, transport=self._transport
            )
        )

    def holder_profile(self, chain: str, mint: str) -> HolderProfile:
        validate_chain(chain)
        validate_mint(mint)
        now = self._clock()
        with self._cache_lock:
            cached = self._holder_cache.get(mint)
            if cached is not None:
                cached_at, profile = cached
                age = (now - cached_at).total_seconds()
                if 0 <= age < self._holder_cache_ttl.total_seconds():
                    return profile
            payload = self._get(f"/tokens/{quote(mint, safe='')}/holders")
        if not isinstance(payload, dict):
            raise MalformedData(self.SERVICE, "expected an object")
        total = payload.get("total")
        accounts = payload.get("accounts")
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise MalformedData(self.SERVICE, "total holder count missing")
        if not isinstance(accounts, list):
            raise MalformedData(self.SERVICE, "accounts missing")
        if any(not isinstance(account, dict) for account in accounts):
            raise MalformedData(self.SERVICE, "holder account entry is not an object")
        ranked_accounts: list[tuple[Decimal, str]] = []
        amounts: list[Decimal] = []
        for account in accounts:
            amount = to_decimal(
                account.get("amount"), service=self.SERVICE, field="amount"
            )
            if amount < 0:
                raise MalformedData(
                    self.SERVICE, "holder account amount cannot be negative"
                )
            amounts.append(amount)
            address = next(
                (
                    account.get(key)
                    for key in ("owner", "address", "wallet")
                    if isinstance(account.get(key), str)
                ),
                None,
            )
            if address:
                try:
                    validate_mint(address)
                except DomainError:
                    continue
                ranked_accounts.append((amount, address))
        share = None
        total_amount = sum(amounts, Decimal(0))
        if amounts and total_amount > 0:
            top10 = sum(sorted(amounts, reverse=True)[:10], Decimal(0))
            share = top10 / total_amount * Decimal(100)
        top_holders = tuple(
            address
            for _, address in sorted(
                ranked_accounts, key=lambda item: item[0], reverse=True
            )[:20]
        )
        profile = HolderProfile(mint, total, share, self.SERVICE, top_holders)
        with self._cache_lock:
            self._holder_cache[mint] = (now, profile)
        return profile
