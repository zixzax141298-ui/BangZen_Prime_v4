"""Optional LunarCrush macro sentiment adapter.

The first integration intentionally measures Solana ecosystem sentiment, not a token's
sentiment. Ticker-only matching is unsafe for memecoins because symbols collide.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from urllib.parse import quote

from bangzen_prime.core.errors import DomainError
from bangzen_prime.core.ports import MarketSentimentObservation
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

BASE_URL = "https://lunarcrush.com/api4"


class LunarCrushSentimentAdapter:
    """Fetch Solana macro sentiment with a bounded in-memory TTL cache."""

    SERVICE = "lunarcrush"
    TOPIC = "solana"

    def __init__(
        self,
        *,
        api_key: str,
        transport: RequestTransport,
        caller: ResilientCaller,
        timeout: float,
        clock,
        cache_ttl_seconds: int = 300,
        max_age_seconds: int = 900,
    ) -> None:
        if not api_key or not api_key.strip():
            raise DomainError("LunarCrush API key is required")
        if not 1 <= cache_ttl_seconds <= 3600:
            raise ValueError("cache_ttl_seconds must be within [1, 3600]")
        if not 1 <= max_age_seconds <= 86400:
            raise ValueError("max_age_seconds must be within [1, 86400]")
        self._key = api_key.strip()
        self._transport = transport
        self._caller = caller
        self._timeout = timeout
        self._clock = clock
        self._ttl = timedelta(seconds=cache_ttl_seconds)
        self._max_age = max_age_seconds
        self._cached: MarketSentimentObservation | None = None
        self._cache_until: datetime | None = None

    def fetch_market_sentiment(self) -> MarketSentimentObservation:
        now = self._clock()
        if (
            self._cached is not None
            and self._cache_until is not None
            and now < self._cache_until
        ):
            return self._cached

        url = f"{BASE_URL}/public/topic/{quote(self.TOPIC, safe='')}/v1"
        request = HttpRequest(
            "GET",
            url,
            {"Authorization": f"Bearer {self._key}", "Accept": "application/json"},
            None,
            self._timeout,
        )
        payload = self._caller.call(
            lambda: request_json(
                service=self.SERVICE, request=request, transport=self._transport
            )
        )
        snapshot = self._parse(payload, now)
        self._cached = snapshot
        self._cache_until = now + self._ttl
        return snapshot

    def _parse(self, payload: Any, now: datetime) -> MarketSentimentObservation:
        if not isinstance(payload, dict):
            raise MalformedData(self.SERVICE, "expected an object")
        config = payload.get("config")
        data = payload.get("data")
        if not isinstance(config, dict) or not isinstance(data, dict):
            raise MalformedData(self.SERVICE, "config or data missing")
        if str(config.get("topic", self.TOPIC)).lower() != self.TOPIC:
            raise MalformedData(self.SERVICE, "response topic mismatch")
        generated = config.get("generated")
        if isinstance(generated, bool) or not isinstance(generated, (int, float)):
            raise MalformedData(self.SERVICE, "generated timestamp missing")
        try:
            generated_at = datetime.fromtimestamp(float(generated), tz=UTC)
        except (OverflowError, OSError, ValueError):
            raise MalformedData(self.SERVICE, "generated timestamp invalid") from None
        age = (now - generated_at).total_seconds()
        if age < -60 or age > self._max_age:
            raise MalformedData(
                self.SERVICE, "sentiment snapshot is stale or future-dated"
            )

        sentiments = data.get("types_sentiment")
        interactions = data.get("types_interactions")
        if not isinstance(sentiments, dict) or not isinstance(interactions, dict):
            raise MalformedData(self.SERVICE, "sentiment breakdown missing")
        weighted = Decimal(0)
        total_weight = Decimal(0)
        for network, raw_sentiment in sentiments.items():
            if network not in interactions:
                continue
            sentiment = to_decimal(
                raw_sentiment, service=self.SERVICE, field="sentiment"
            )
            weight = to_decimal(
                interactions[network], service=self.SERVICE, field="interactions"
            )
            if not Decimal(0) <= sentiment <= Decimal(100) or weight < 0:
                raise MalformedData(self.SERVICE, "sentiment values out of range")
            weighted += sentiment * weight
            total_weight += weight
        if total_weight <= 0:
            raise MalformedData(self.SERVICE, "no weighted social interactions")
        sentiment_pct = (weighted / total_weight).quantize(Decimal("0.01"))

        def count(field: str) -> int:
            raw = data.get(field, 0)
            if isinstance(raw, bool) or not isinstance(raw, int) or raw < 0:
                raise MalformedData(self.SERVICE, f"{field} invalid")
            return raw

        trend = data.get("trend", "unknown")
        if trend not in {"up", "down", "flat", "unknown", None}:
            raise MalformedData(self.SERVICE, "trend invalid")
        return MarketSentimentObservation(
            topic=self.TOPIC,
            sentiment_pct=sentiment_pct,
            interactions_24h=count("interactions_24h"),
            contributors_24h=count("num_contributors"),
            posts_24h=count("num_posts"),
            trend=trend or "unknown",
            generated_at=generated_at,
            source=self.SERVICE,
        )
