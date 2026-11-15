"""Evidence-based token lifecycle phase classification.

Phases describe pair age, not a buy/sell decision. Missing creation timestamps stay
UNKNOWN; liquidity thresholds are deliberately not used to assign or reject a phase.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from bangzen_prime.core.shared import ensure_utc


class TokenPhase(StrEnum):
    UNKNOWN = "UNKNOWN"
    LAUNCH = "LAUNCH"
    EARLY = "EARLY"
    GROWTH = "GROWTH"
    MATURE = "MATURE"
    CEX_LISTED = "CEX_LISTED"


@dataclass(frozen=True)
class PhaseAssessment:
    phase: TokenPhase
    pair_age_seconds: int | None
    suggested_refresh_seconds: int


def assess_token_phase(
    pair_created_at: datetime | None,
    now: datetime,
    *,
    verified_cex_listing: bool = False,
) -> PhaseAssessment:
    """Classify observed lifecycle context; never rejects a token.

    CEX_LISTED is reserved for an independently verified listing signal. This
    repository does not yet provide that signal, so callers must not infer it.
    """
    if verified_cex_listing:
        return PhaseAssessment(TokenPhase.CEX_LISTED, None, 3600)
    if pair_created_at is None:
        return PhaseAssessment(TokenPhase.UNKNOWN, None, 60)

    age = (ensure_utc(now) - ensure_utc(pair_created_at)).total_seconds()
    if age < 0:
        return PhaseAssessment(TokenPhase.UNKNOWN, None, 60)
    age_seconds = int(age)
    if age_seconds <= 3600:
        return PhaseAssessment(TokenPhase.LAUNCH, age_seconds, 15)
    if age_seconds <= 86400:
        return PhaseAssessment(TokenPhase.EARLY, age_seconds, 60)
    if age_seconds <= 604800:
        return PhaseAssessment(TokenPhase.GROWTH, age_seconds, 300)
    return PhaseAssessment(TokenPhase.MATURE, age_seconds, 900)
