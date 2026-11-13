import logging
import re
from dataclasses import dataclass
from decimal import Decimal

logger = logging.getLogger(__name__)

TREND_KEYWORDS: tuple[str, ...] = (
    "ai",
    "meme",
    "cat",
    "dog",
    "trump",
    "elon",
    "cult",
    "agent",
    "pepe",
    "quantum",
    "neural",
    "solana",
    "autonomous",
    "sentient",
)


@dataclass(frozen=True)
class MetadataScoreReport:
    score: Decimal
    matched_keywords: tuple[str, ...]
    reason: str


class MetadataScorer:
    """
    Memberikan skor bonus berdasarkan narasi trending pada metadata token.
    Skor maksimal: 10.
    """

    def __init__(self, keywords: tuple[str, ...] = TREND_KEYWORDS):
        self.keywords = keywords
        self._patterns = {
            kw: re.compile(r"\b" + re.escape(kw) + r"\b") for kw in self.keywords
        }

    def score_narrative(
        self, description: str, website: str = ""
    ) -> MetadataScoreReport:
        clean_desc = (description or "").strip().lower()
        clean_web = (website or "").strip().lower()
        combined_text = f"{clean_desc} {clean_web}".strip()

        if not combined_text:
            return MetadataScoreReport(
                score=Decimal(0), matched_keywords=(), reason="empty_metadata"
            )

        matched: list[str] = []
        for kw, pattern in self._patterns.items():
            if pattern.search(combined_text):
                matched.append(kw)

        if not matched:
            return MetadataScoreReport(
                score=Decimal(0), matched_keywords=(), reason="no_trending_keywords"
            )

        raw_bonus = 3 + (len(matched) - 1) * 2
        bonus = Decimal(str(min(10, max(0, raw_bonus))))

        logger.debug(f"[MetadataScorer] Found keywords {matched} -> Score: {bonus}")

        return MetadataScoreReport(
            score=bonus,
            matched_keywords=tuple(matched),
            reason=f"matched_{len(matched)}_keywords",
        )
