"""Phase-aware heuristic scoring. Scores rank candidates; they are not probabilities."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from bangzen_prime.domain.values import non_negative, percent

WEIGHTS = {
    "liquidity": Decimal("0.35"),
    "volume": Decimal("0.20"),
    "safety": Decimal("0.30"),
    "momentum": Decimal("0.15"),
}
# Early launches are assessed on evidence that can exist at that age. Liquidity remains
# a scored feature, but is not allowed to dominate the initial discovery phase.
EARLY_PHASE_WEIGHTS = {
    "liquidity": Decimal("0.15"),
    "volume": Decimal("0.30"),
    "safety": Decimal("0.35"),
    "momentum": Decimal("0.20"),
}
LIQUIDITY_FULL_SCORE_USD = Decimal("100000")
VOLUME_FULL_SCORE_USD = Decimal("500000")
RSI_CENTER = Decimal("55")
_EARLY_PHASES = frozenset({"UNKNOWN", "LAUNCH", "EARLY"})
_VALID_PHASES = frozenset({"UNKNOWN", "LAUNCH", "EARLY", "GROWTH", "MATURE", "CEX_LISTED"})


def _clip(value: Decimal) -> Decimal:
    return min(Decimal(100), max(Decimal(0), value))


@dataclass(frozen=True)
class ScoreBreakdown:
    liquidity: Decimal
    volume: Decimal
    safety: Decimal
    momentum: Decimal
    total: Decimal

    @property
    def confidence(self) -> Decimal:
        """Heuristic confidence in [0, 1] derived from the score. Not a probability."""
        return self.total / Decimal(100)


def score_token(
    *, liquidity_usd: Decimal, volume_24h_usd: Decimal, risk_score: Decimal,
    rsi_value: Decimal, phase: str = "MATURE",
) -> ScoreBreakdown:
    if phase not in _VALID_PHASES:
        raise ValueError("unsupported token lifecycle phase")
    liquidity = non_negative(liquidity_usd, "liquidity_usd")
    volume = non_negative(volume_24h_usd, "volume_24h_usd")
    risk = percent(risk_score, "risk_score")
    rsi_v = percent(rsi_value, "rsi")
    parts = {
        "liquidity": _clip(liquidity / LIQUIDITY_FULL_SCORE_USD * 100),
        "volume": _clip(volume / VOLUME_FULL_SCORE_USD * 100),
        "safety": _clip(Decimal(100) - risk),
        "momentum": _clip(Decimal(100) - abs(rsi_v - RSI_CENTER) * 2),
    }
    weights = EARLY_PHASE_WEIGHTS if phase in _EARLY_PHASES else WEIGHTS
    total = sum((parts[k] * weights[k] for k in weights), Decimal(0))
    return ScoreBreakdown(
        liquidity=parts["liquidity"].quantize(Decimal("0.01")),
        volume=parts["volume"].quantize(Decimal("0.01")),
        safety=parts["safety"].quantize(Decimal("0.01")),
        momentum=parts["momentum"].quantize(Decimal("0.01")),
        total=total.quantize(Decimal("0.01")),
    )
