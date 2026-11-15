"""Fail-closed orchestration for mint owner and Token-2022 extension evidence."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

from bangzen_prime.core.shared import ensure_utc
from bangzen_prime.discovery.tokens import validate_mint
from bangzen_prime.security.token_2022_extension_evidence import (
    UNAVAILABLE,
    Token2022ExtensionEvidence,
)
from bangzen_prime.security.token_2022_extensions import REJECTED
from bangzen_prime.security.token_2022_risk import (
    APPROVED,
    BLOCKED,
    HOLD,
    evaluate_token_2022_risk,
)
from bangzen_prime.security.token_programs import (
    TOKEN_2022_PROGRAM_ID,
    TOKEN_PROGRAM_ID,
)


class Token2022ExtensionReader(Protocol):
    def read(self, mint: str) -> Token2022ExtensionEvidence: ...


@dataclass(frozen=True)
class TokenProgramAssessment:
    mint: str
    token_program: str | None
    status: str
    reason_codes: tuple[str, ...]
    evidence: Token2022ExtensionEvidence | None = None

    @property
    def approved(self) -> bool:
        # Classic SPL Token is explicitly identified and does not use Token-2022 extensions.
        return self.status in {APPROVED, "NOT_APPLICABLE"}


class TokenProgramEvidenceUseCase:
    """Resolve the exact mint owner, then apply Token-2022's deterministic veto.

    A missing reader, provider error, unknown owner, identity mismatch, stale or partial
    evidence is HOLD. Only a structurally confirmed classic SPL Token mint bypasses Token-2022 extension parsing.
    """

    def __init__(self, reader: Token2022ExtensionReader | None) -> None:
        if reader is not None and not callable(getattr(reader, "read", None)):
            raise ValueError("reader must provide read(mint)")
        self._reader = reader

    def execute(
        self,
        mint: str,
        *,
        now: datetime,
        max_age: timedelta,
    ) -> TokenProgramAssessment:
        validate_mint(mint)
        if not isinstance(max_age, timedelta) or max_age <= timedelta(0):
            raise ValueError("max_age must be a positive timedelta")
        if self._reader is None:
            return TokenProgramAssessment(
                mint, None, HOLD, ("TOKEN_PROGRAM_EVIDENCE_UNAVAILABLE",)
            )
        try:
            evidence = self._reader.read(mint)
        except Exception:
            # Do not leak provider URLs, credentials, or raw exception payloads.
            return TokenProgramAssessment(
                mint, None, HOLD, ("TOKEN_PROGRAM_EVIDENCE_UNAVAILABLE",)
            )
        if not isinstance(evidence, Token2022ExtensionEvidence):
            return TokenProgramAssessment(
                mint, None, HOLD, ("TOKEN_PROGRAM_EVIDENCE_INVALID",)
            )
        if evidence.mint != mint:
            return TokenProgramAssessment(
                mint,
                evidence.token_program,
                BLOCKED,
                ("TOKEN2022_MINT_MISMATCH",),
                evidence,
            )

        age = ensure_utc(now) - ensure_utc(evidence.observed_at)
        if age < timedelta(0) or age > max_age:
            return TokenProgramAssessment(
                mint,
                evidence.token_program,
                HOLD,
                ("TOKEN_PROGRAM_EVIDENCE_STALE",),
                evidence,
            )

        # The Helius extension reader reports a non-Token-2022 owner as REJECTED.
        # Only an exact classic SPL Token owner + expected reason is a valid N/A result.
        if (
            evidence.token_program == TOKEN_PROGRAM_ID
            and evidence.validation_status == REJECTED
            and evidence.account_data_length == 82
            and "CLASSIC_SPL_MINT_CONFIRMED" in evidence.reason_codes
        ):
            return TokenProgramAssessment(
                mint,
                TOKEN_PROGRAM_ID,
                "NOT_APPLICABLE",
                ("CLASSIC_SPL_TOKEN_PROGRAM",),
                evidence,
            )

        if evidence.token_program != TOKEN_2022_PROGRAM_ID:
            if evidence.validation_status == UNAVAILABLE:
                return TokenProgramAssessment(
                    mint,
                    evidence.token_program,
                    HOLD,
                    ("TOKEN_PROGRAM_EVIDENCE_UNAVAILABLE",),
                    evidence,
                )
            return TokenProgramAssessment(
                mint,
                evidence.token_program,
                BLOCKED,
                ("TOKEN_PROGRAM_UNSUPPORTED",),
                evidence,
            )

        decision = evaluate_token_2022_risk(
            evidence, expected_mint=mint, now=now, max_age=max_age
        )
        return TokenProgramAssessment(
            mint,
            TOKEN_2022_PROGRAM_ID,
            decision.status,
            decision.reason_codes,
            evidence,
        )
