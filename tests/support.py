"""Shared test helpers: deterministic fakes for HTTP, clock, and notifier. No network."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from bangzen_prime.infrastructure.http import HttpResponse
from bangzen_prime.infrastructure.resilience.policies import FakeClock

SOL_MINT = "So11111111111111111111111111111111111111112"
TOKEN_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
PAIR_ADDRESS = "HxFLKUAmAMLz1jtT3hbvCMELwH5H9tpM2QugP8sKyfhc"
START = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def json_response(payload: object, status: int = 200, headers: dict | None = None) -> HttpResponse:
    return HttpResponse(status, json.dumps(payload).encode("utf-8"), headers or {})


class RecordingTransport:
    """Routes URLs to handlers. Records every call; an unrouted URL fails loudly."""

    def __init__(self, handler: Callable[[str], HttpResponse | Exception]) -> None:
        self._handler = handler
        self.calls: list[str] = []

    def __call__(self, *args, **kwargs) -> HttpResponse:
        # Production has two transport shapes: legacy (url, timeout) and request-object
        # (HttpRequest). The fake accepts both so each adapter's real calling convention is tested.
        if len(args) == 1 and not isinstance(args[0], str):
            url = args[0].url
        else:
            url = args[0] if args else kwargs["url"]
        self.calls.append(url)
        result = self._handler(url)
        if isinstance(result, Exception):
            raise result
        return result


class RecordingNotifier:
    def __init__(self, fail_times: int = 0) -> None:
        self.sent: list[str] = []
        self._fail_times = fail_times

    def send(self, text: str) -> None:
        if self._fail_times > 0:
            self._fail_times -= 1
            raise RuntimeError("simulated notifier outage")
        self.sent.append(text)


def pair_payload(*, price: str = "0.00100", liquidity: float = 200000.0,
                 volume: float = 300000.0, chain: str = "solana", mint: str = TOKEN_MINT,
                 pair_address: str = PAIR_ADDRESS, symbol: str = "TEST", created_ms: int | None = None) -> dict:
    extra = {} if created_ms is None else {"pairCreatedAt": created_ms}
    return {
        **extra,
        "chainId": chain,
        "dexId": "raydium",
        "pairAddress": pair_address,
        "baseToken": {"address": mint, "symbol": symbol, "name": "Test"},
        "quoteToken": {"address": SOL_MINT, "symbol": "SOL"},
        "priceUsd": price,
        "liquidity": {"usd": liquidity},
        "volume": {"h24": volume},
    }


def safety_payload(*, score: float = 10.0, rugged: bool | None = None,
                   risks: list | None = None) -> dict:
    payload: dict = {"score_normalised": score, "risks": risks or []}
    if rugged is not None:
        payload["rugged"] = rugged
    return payload


def clock_at(seconds: int = 0) -> FakeClock:
    clock = FakeClock(START)
    clock.advance(seconds)
    return clock


def d(value: str) -> Decimal:
    return Decimal(value)
