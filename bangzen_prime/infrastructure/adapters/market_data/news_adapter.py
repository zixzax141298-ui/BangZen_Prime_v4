import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

import httpx
from defusedxml import ElementTree as ET

logger = logging.getLogger(__name__)

TARGET_KEYWORDS = ("Elon", "Trump", "AI", "BlackRock", "SEC")
RSS_FEEDS = (
    "https://www.coindesk.com/arc/outboundfeeds/rss/",
    "https://cointelegraph.com/rss",
)


@dataclass(frozen=True)
class NewsReport:
    active_keywords: tuple[str, ...]
    fetched_at: datetime
    is_cached: bool
    reason: str = ""


class NewsScraperAdapter:
    def __init__(
        self,
        transport: httpx.AsyncClient,
        clock: Callable[[], datetime],
        cache_ttl_sec: int = 300,
    ):
        self.transport = transport
        self.clock = clock
        self.cache_ttl_sec = cache_ttl_sec
        self._cache: dict = {"result": None, "ts": 0.0}

    def _parse_rss(self, content: str) -> set[str]:
        found = set()
        try:
            root = ET.fromstring(content.strip())
            corpus = " ".join(
                [
                    item.text
                    for item in root.iter()
                    if item.tag.lower().endswith(("title", "description", "summary"))
                    and item.text
                ]
            )
            for kw in TARGET_KEYWORDS:
                if re.search(r"\b" + re.escape(kw) + r"\b", corpus, re.IGNORECASE):
                    found.add(kw)
        except Exception:
            pass  # nosec B110
        return found

    async def fetch_active_keywords(self, force: bool = False) -> NewsReport:
        now_ts = self.clock().timestamp()
        if (
            not force
            and self._cache["result"]
            and (now_ts - self._cache["ts"] < self.cache_ttl_sec)
        ):
            return NewsReport(
                self._cache["result"].active_keywords,
                self._cache["result"].fetched_at,
                True,
                "cache_hit",
            )

        active = set()
        for url in RSS_FEEDS:
            try:
                resp = await self.transport.get(url, timeout=6.0)
                if resp.status_code == 200:
                    active.update(self._parse_rss(resp.text))
            except Exception:
                pass  # nosec B110

        result = NewsReport(tuple(sorted(active)), self.clock(), False, "fetched")
        self._cache = {"result": result, "ts": now_ts}
        return result
