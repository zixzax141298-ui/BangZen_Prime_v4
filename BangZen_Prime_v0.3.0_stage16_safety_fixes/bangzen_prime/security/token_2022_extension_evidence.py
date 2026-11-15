"""Provider-neutral Token-2022 extension evidence; not a safety verdict."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from bangzen_prime.core.errors import DomainError
from bangzen_prime.discovery.tokens import validate_mint
from bangzen_prime.security.token_2022_extension_config import (
    ParsedToken2022Configuration,
)
from bangzen_prime.security.token_2022_extensions import (
    PARTIAL,
    REJECTED,
    VERIFIED,
    Token2022ExtensionRecord,
)

UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True)
class Token2022ExtensionEvidence:
    mint: str
    validation_status: str
    observed_at: datetime
    source: str
    source_record_id: str
    slot: int
    token_program: str | None = None
    account_data_length: int | None = None
    extensions: tuple[Token2022ExtensionRecord, ...] = ()
    risk_flags: tuple[str, ...] = ()
    unknown_extension_ids: tuple[int, ...] = ()
    reason_codes: tuple[str, ...] = ()
    configuration: ParsedToken2022Configuration | None = None

    def __post_init__(self) -> None:
        validate_mint(self.mint)
        if self.validation_status not in {VERIFIED, PARTIAL, UNAVAILABLE, REJECTED}:
            raise DomainError("invalid Token-2022 extension validation status")
        if (
            not isinstance(self.observed_at, datetime)
            or self.observed_at.tzinfo is None
            or self.observed_at.utcoffset() is None
        ):
            raise DomainError("observed_at must be timezone-aware")
        if not isinstance(self.source, str) or not self.source.strip():
            raise DomainError("source is required")
        if (
            not isinstance(self.source_record_id, str)
            or not self.source_record_id.strip()
        ):
            raise DomainError("source_record_id is required")
        if (
            isinstance(self.slot, bool)
            or not isinstance(self.slot, int)
            or self.slot < 0
        ):
            raise DomainError("slot must be a non-negative integer")
        if self.account_data_length is not None and (
            isinstance(self.account_data_length, bool)
            or not isinstance(self.account_data_length, int)
            or self.account_data_length < 0
        ):
            raise DomainError("account_data_length must be non-negative")
        if any(
            isinstance(value, bool)
            or not isinstance(value, int)
            or not 0 <= value <= 65535
            for value in self.unknown_extension_ids
        ):
            raise DomainError("unknown extension IDs must be u16 values")
        if self.validation_status == VERIFIED and self.unknown_extension_ids:
            raise DomainError("VERIFIED evidence cannot contain unknown extension IDs")
        if any(
            not isinstance(record, Token2022ExtensionRecord)
            for record in self.extensions
        ):
            raise DomainError("extensions must contain validated extension records")
        if self.configuration is not None and not isinstance(
            self.configuration, ParsedToken2022Configuration
        ):
            raise DomainError(
                "configuration must be parsed Token-2022 configuration evidence"
            )
        if (
            self.validation_status == VERIFIED
            and self.configuration is not None
            and (self.configuration.validation_status != VERIFIED)
        ):
            raise DomainError(
                "VERIFIED evidence cannot contain partial or rejected configuration"
            )

    @property
    def extension_names(self) -> tuple[str, ...]:
        return tuple(record.name for record in self.extensions)
