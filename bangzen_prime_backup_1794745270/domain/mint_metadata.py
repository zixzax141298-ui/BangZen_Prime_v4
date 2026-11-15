"""Provider-neutral evidence for validated Solana mint account metadata.

This model records only facts decoded from the mint account. It is not a complete
Token-2022 extension audit and must never be interpreted as a token safety verdict.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from bangzen_prime.domain.tokens import validate_mint
from bangzen_prime.errors import DomainError

if TYPE_CHECKING:
    from bangzen_prime.domain.quote_economics import VerifiedMintDecimals

VERIFIED = "VERIFIED"
UNAVAILABLE = "UNAVAILABLE"
REJECTED = "REJECTED"
SUPPORTED_TOKEN_PROGRAMS = frozenset(
    {
        "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA",
        "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb",
    }
)


@dataclass(frozen=True)
class MintMetadataEvidence:
    """One account observation with provenance and explicit validation outcome."""

    mint: str
    validation_status: str
    observed_at: datetime
    source: str
    slot: int | None = None
    token_program: str | None = None
    decimals: int | None = None
    supply_raw: int | None = None
    is_initialized: bool | None = None
    account_data_length: int | None = None
    additional_data_length: int = 0
    reason_codes: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        validate_mint(self.mint)
        if self.validation_status not in {VERIFIED, UNAVAILABLE, REJECTED}:
            raise DomainError("invalid mint metadata validation status")
        if (
            not isinstance(self.observed_at, datetime)
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() is None
        ):
            raise DomainError("mint metadata observed_at must be timezone-aware")
        if not isinstance(self.source, str) or not self.source.strip():
            raise DomainError("mint metadata source is required")
        if self.slot is not None and (
            isinstance(self.slot, bool)
            or not isinstance(self.slot, int)
            or self.slot < 0
        ):
            raise DomainError("mint metadata slot must be a non-negative integer")
        if self.validation_status == VERIFIED:
            if self.token_program not in SUPPORTED_TOKEN_PROGRAMS:
                raise DomainError("verified mint must use an allowlisted Token Program")
            if (
                isinstance(self.decimals, bool)
                or not isinstance(self.decimals, int)
                or not 0 <= self.decimals <= 255
            ):
                raise DomainError("verified mint decimals must be a u8")
            if (
                isinstance(self.supply_raw, bool)
                or not isinstance(self.supply_raw, int)
                or not 0 <= self.supply_raw <= 2**64 - 1
            ):
                raise DomainError("verified mint supply must be a u64")
            if self.is_initialized is not True:
                raise DomainError("verified mint must be initialized")
            if self.slot is None:
                raise DomainError("verified mint must include RPC context slot")
        elif self.decimals is not None:
            raise DomainError(
                "non-verified mint evidence must not expose usable decimals"
            )

    def to_verified_decimals(self) -> VerifiedMintDecimals:
        """Create the quote-domain evidence only after this account was verified."""
        if self.validation_status != VERIFIED:
            raise DomainError("mint metadata is not VERIFIED")
        from bangzen_prime.domain.quote_economics import VerifiedMintDecimals

        assert self.decimals is not None and self.slot is not None
        return VerifiedMintDecimals(
            mint=self.mint,
            decimals=self.decimals,
            source=f"{self.source}:{self.token_program}",
            observed_at=self.observed_at,
            validation_status=VERIFIED,
            slot=self.slot,
        )
