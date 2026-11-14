"""Evidence-led token lifecycle states; lifecycle is descriptive, never execution approval."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from bangzen_prime.domain.shared import ensure_utc
from bangzen_prime.domain.tokens import validate_chain, validate_mint
from bangzen_prime.errors import DomainError


class LifecyclePhase(StrEnum):
    DISCOVERED = "DISCOVERED"
    LAUNCH = "LAUNCH"
    EARLY_ACTIVITY = "EARLY_ACTIVITY"
    EXPANSION = "EXPANSION"
    CONSOLIDATION = "CONSOLIDATION"
    DECLINING = "DECLINING"
    MIGRATING = "MIGRATING"
    CEX_LISTED = "CEX_LISTED"
    INACTIVE = "INACTIVE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class LifecycleObservation:
    chain: str
    mint: str
    phase: LifecyclePhase
    observed_at: datetime
    reason: str
    evidence: dict[str, Any]

    def __post_init__(self) -> None:
        validate_chain(self.chain)
        validate_mint(self.mint)
        if not isinstance(self.phase, LifecyclePhase):
            raise DomainError("phase must be a LifecyclePhase")
        ensure_utc(self.observed_at)
        if not isinstance(self.reason, str) or len(self.reason) > 256:
            raise DomainError("reason must be a string of at most 256 characters")
        if not isinstance(self.evidence, dict):
            raise DomainError("evidence must be a dictionary")
