"""Deterministic, fail-closed interpretation of Token-2022 mint evidence.

This module reports a veto/hold outcome; it never authorizes execution or assigns a score.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from bangzen_prime.core.errors import DomainError
from bangzen_prime.core.shared import ensure_utc
from bangzen_prime.security.token_2022_extension_evidence import (
    Token2022ExtensionEvidence,
)
from bangzen_prime.security.token_2022_extensions import REJECTED, VERIFIED

APPROVED = "APPROVED"
BLOCKED = "BLOCKED"
HOLD = "HOLD"

# These states make ordinary transfer-based entry impossible or explicitly paused.
HARD_VETO_FLAGS = frozenset(
    {
        "TOKEN_TRANSFERS_PAUSED",
        "NON_TRANSFERABLE",
        "DEFAULT_ACCOUNTS_FROZEN",
        "DEFAULT_ACCOUNTS_UNINITIALIZED",
    }
)
# These features require additional independent analysis/cost modelling; presence alone
# is not proof of maliciousness and is deliberately not converted into a permanent ban.
REVIEW_FLAGS = frozenset(
    {
        "TRANSFER_FEE_NONZERO",
        "PERMANENT_DELEGATE_ACTIVE",
        "TRANSFER_HOOK_PROGRAM_CONFIGURED",
        "TRANSFER_FEE_CONFIG_AUTHORITY_PRESENT",
        "TRANSFER_FEE_WITHDRAW_AUTHORITY_PRESENT",
        "TRANSFER_HOOK_AUTHORITY_PRESENT",
        "MINT_CLOSE_AUTHORITY_ACTIVE",
        "INTEREST_RATE_AUTHORITY_PRESENT",
        "PAUSABLE_AUTHORITY_PRESENT",
        "PERMISSIONED_BURN_AUTHORITY_PRESENT",
        "METADATA_POINTER_AUTHORITY_PRESENT",
        "GROUP_POINTER_AUTHORITY_PRESENT",
        "GROUP_MEMBER_POINTER_AUTHORITY_PRESENT",
        "SCALED_UI_AMOUNT_AUTHORITY_PRESENT",
    }
)


@dataclass(frozen=True)
class Token2022RiskDecision:
    status: str
    mint: str
    reason_codes: tuple[str, ...]
    observed_at: datetime | None
    source: str | None

    @property
    def approved(self) -> bool:
        return self.status == APPROVED


def evaluate_token_2022_risk(
    evidence: Token2022ExtensionEvidence | None,
    *,
    expected_mint: str,
    now: datetime,
    max_age: timedelta,
) -> Token2022RiskDecision:
    """Evaluate validated evidence for one exact mint; missing/uncertain data never passes."""
    if not isinstance(expected_mint, str) or not expected_mint.strip():
        raise DomainError("expected_mint is required")
    now = ensure_utc(now)
    if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
        raise DomainError("max_age must be a positive timedelta")

    if evidence is None:
        return Token2022RiskDecision(
            HOLD, expected_mint, ("TOKEN2022_EVIDENCE_UNAVAILABLE",), None, None
        )
    if not isinstance(evidence, Token2022ExtensionEvidence):
        raise DomainError("evidence must be Token2022ExtensionEvidence")
    if evidence.mint != expected_mint:
        return Token2022RiskDecision(
            BLOCKED,
            expected_mint,
            ("TOKEN2022_MINT_MISMATCH",),
            evidence.observed_at,
            evidence.source,
        )

    age = now - ensure_utc(evidence.observed_at)
    if age < timedelta(0) or age > max_age:
        return Token2022RiskDecision(
            HOLD,
            expected_mint,
            ("TOKEN2022_EVIDENCE_STALE",),
            evidence.observed_at,
            evidence.source,
        )

    if evidence.validation_status == REJECTED:
        return Token2022RiskDecision(
            BLOCKED,
            expected_mint,
            ("TOKEN2022_EVIDENCE_REJECTED", *evidence.reason_codes),
            evidence.observed_at,
            evidence.source,
        )
    if evidence.validation_status != VERIFIED:
        return Token2022RiskDecision(
            HOLD,
            expected_mint,
            ("TOKEN2022_EVIDENCE_NOT_VERIFIED", *evidence.reason_codes),
            evidence.observed_at,
            evidence.source,
        )
    if (
        evidence.configuration is None
        or evidence.configuration.validation_status != VERIFIED
    ):
        return Token2022RiskDecision(
            HOLD,
            expected_mint,
            ("TOKEN2022_CONFIG_NOT_VERIFIED",),
            evidence.observed_at,
            evidence.source,
        )

    flags = set(evidence.risk_flags) | set(evidence.configuration.risk_flags)
    hard = tuple(sorted(flags & HARD_VETO_FLAGS))
    if hard:
        return Token2022RiskDecision(
            BLOCKED,
            expected_mint,
            ("TOKEN2022_HARD_VETO", *hard),
            evidence.observed_at,
            evidence.source,
        )
    review = tuple(sorted(flags & REVIEW_FLAGS))
    if review:
        return Token2022RiskDecision(
            HOLD,
            expected_mint,
            ("TOKEN2022_REVIEW_REQUIRED", *review),
            evidence.observed_at,
            evidence.source,
        )
    return Token2022RiskDecision(
        APPROVED,
        expected_mint,
        ("TOKEN2022_CONFIG_VERIFIED_NO_KNOWN_VETO_FLAGS",),
        evidence.observed_at,
        evidence.source,
    )
