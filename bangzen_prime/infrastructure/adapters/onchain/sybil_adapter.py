"""Sybil-cluster evidence adapter with bounded Helius usage and safe caching."""

from __future__ import annotations

import asyncio
import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Callable

import httpx

logger = logging.getLogger(__name__)
_WINDOW_SECONDS = 60.0


@dataclass(frozen=True)
class SybilReport:
    # None means the evidence is inconclusive; never coerce it to safe or bundled.
    is_bundled: bool | None
    reason: str
    cluster_size: int
    unavailable_count: int
    available: bool


class _SlidingWindowBudget:
    """Non-blocking cap shared by all RPC calls made by one adapter instance."""

    def __init__(self, calls_per_minute: int, clock: Callable[[], float]) -> None:
        if (
            not isinstance(calls_per_minute, int)
            or isinstance(calls_per_minute, bool)
            or calls_per_minute <= 0
        ):
            raise ValueError("max_rpc_calls_per_minute must be a positive integer")
        self._limit = calls_per_minute
        self._clock = clock
        self._stamps: deque[float] = deque()
        self._lock = threading.Lock()

    def try_acquire(self) -> bool:
        now = self._clock()
        with self._lock:
            while self._stamps and now - self._stamps[0] >= _WINDOW_SECONDS:
                self._stamps.popleft()
            if len(self._stamps) >= self._limit:
                return False
            self._stamps.append(now)
            return True


class SybilAdapter:
    def __init__(
        self,
        helius_rpc_url: str,
        timeout: float = 10.0,
        *,
        cache_ttl_seconds: float = 300.0,
        max_rpc_calls_per_minute: int = 30,
        max_concurrent_holders: int = 4,
        clock: Callable[[], float] | None = None,
    ):
        if not isinstance(helius_rpc_url, str):
            raise ValueError("helius_rpc_url must be a string")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        if cache_ttl_seconds < 0:
            raise ValueError("cache_ttl_seconds must not be negative")
        if (
            not isinstance(max_concurrent_holders, int)
            or isinstance(max_concurrent_holders, bool)
            or max_concurrent_holders <= 0
        ):
            raise ValueError("max_concurrent_holders must be a positive integer")
        self.helius_rpc_url = helius_rpc_url
        self.timeout = timeout
        self.cache_ttl_seconds = cache_ttl_seconds
        self._clock = clock or time.monotonic
        self._budget = _SlidingWindowBudget(max_rpc_calls_per_minute, self._clock)
        self._holder_semaphore = asyncio.Semaphore(max_concurrent_holders)
        self._cache: dict[str, tuple[float, str, str | None]] = {}
        self._inflight: dict[str, asyncio.Task[tuple[str, str | None]]] = {}
        self._inflight_lock = asyncio.Lock()

    async def _rpc_call(self, client: httpx.AsyncClient, method: str, params: list) -> dict:
        if not self._budget.try_acquire():
            raise RuntimeError("helius_request_budget_exhausted")
        payload = {"jsonrpc": "2.0", "id": 1, "method": method, "params": params}
        resp = await client.post(self.helius_rpc_url, json=payload, timeout=self.timeout)
        resp.raise_for_status()
        data = resp.json()
        if not isinstance(data, dict) or data.get("error") is not None:
            raise ValueError("invalid RPC response")
        return data

    async def _find_funder(
        self, client: httpx.AsyncClient, holder_address: str
    ) -> tuple[str, str | None]:
        try:
            async with self._holder_semaphore:
                sigs_resp = await self._rpc_call(
                    client, "getSignaturesForAddress", [holder_address, {"limit": 20}]
                )
                signatures = sigs_resp.get("result")
                if not isinstance(signatures, list) or not signatures:
                    return "UNAVAILABLE", None

                oldest = signatures[-1]
                oldest_sig = oldest.get("signature") if isinstance(oldest, dict) else None
                if not isinstance(oldest_sig, str) or not oldest_sig:
                    return "UNAVAILABLE", None

                tx_resp = await self._rpc_call(
                    client,
                    "getTransaction",
                    [oldest_sig, {"encoding": "jsonParsed", "maxSupportedTransactionVersion": 0}],
                )
                tx_result = tx_resp.get("result")
                if not isinstance(tx_result, dict):
                    return "UNAVAILABLE", None

                transaction = tx_result.get("transaction")
                message = transaction.get("message") if isinstance(transaction, dict) else None
                account_keys = message.get("accountKeys") if isinstance(message, dict) else None
                if not isinstance(account_keys, list) or not account_keys:
                    return "UNAVAILABLE", None

                first_key = account_keys[0]
                fee_payer = first_key.get("pubkey") if isinstance(first_key, dict) else first_key
                if not isinstance(fee_payer, str) or not fee_payer:
                    return "UNAVAILABLE", None
                if fee_payer == holder_address:
                    return "SELF", None
                return "FUNDED", fee_payer
        except Exception as exc:
            logger.debug("Sybil funder lookup unavailable: %s", type(exc).__name__)
            return "UNAVAILABLE", None

    async def _lookup_holder(
        self, client: httpx.AsyncClient, holder_address: str
    ) -> tuple[str, str | None]:
        now = self._clock()
        cached = self._cache.get(holder_address)
        if cached is not None:
            cached_at, status, funder = cached
            if now >= cached_at and now - cached_at < self.cache_ttl_seconds:
                return status, funder
            self._cache.pop(holder_address, None)

        async with self._inflight_lock:
            task = self._inflight.get(holder_address)
            if task is None:
                task = asyncio.create_task(self._find_funder(client, holder_address))
                self._inflight[holder_address] = task

        try:
            status, funder = await asyncio.shield(task)
            # Only complete, determinate observations are reusable. Never cache errors/unknowns.
            if status in ("SELF", "FUNDED"):
                self._cache[holder_address] = (self._clock(), status, funder)
            return status, funder
        finally:
            if task.done():
                async with self._inflight_lock:
                    if self._inflight.get(holder_address) is task:
                        self._inflight.pop(holder_address, None)

    async def check_sybil_cluster(self, mint: str, top_holders: list) -> SybilReport:
        del mint  # Holder funding relationships are evaluated independently of token metadata.
        if not self.helius_rpc_url.strip():
            return SybilReport(None, "provider_not_configured", 0, 0, False)
        if not isinstance(top_holders, (list, tuple)):
            return SybilReport(None, "invalid_holder_evidence", 0, 0, False)

        max_holders, min_cluster = 20, 3
        addresses: list[str] = []
        seen: set[str] = set()
        for holder in top_holders[:max_holders]:
            if isinstance(holder, dict):
                address = holder.get("address") or holder.get("owner") or holder.get("wallet")
            else:
                address = holder
            if isinstance(address, str) and address and address not in seen:
                seen.add(address)
                addresses.append(address)

        if len(addresses) < min_cluster:
            return SybilReport(None, "insufficient_holder_evidence", 0, 0, False)

        funder_map: dict[str, list[str]] = {}
        unavailable = 0
        async with httpx.AsyncClient() as client:
            observations = await asyncio.gather(
                *(self._lookup_holder(client, holder) for holder in addresses)
            )

        for holder, (status, funder) in zip(addresses, observations):
            if status == "FUNDED" and funder:
                funder_map.setdefault(funder, []).append(holder)
            elif status == "UNAVAILABLE":
                unavailable += 1

        best_funder, best_holders = None, []
        for funder, holders in funder_map.items():
            if len(holders) > len(best_holders):
                best_funder, best_holders = funder, holders

        best_size = len(best_holders)
        if best_size >= min_cluster:
            return SybilReport(
                True, f"sybil_cluster_{best_funder[:8]}", best_size, unavailable, True
            )
        if unavailable:
            return SybilReport(None, "funder_evidence_incomplete", best_size, unavailable, False)
        return SybilReport(False, "safe_no_cluster", best_size, 0, True)
