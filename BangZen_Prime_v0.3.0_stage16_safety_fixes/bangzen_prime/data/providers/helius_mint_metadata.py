"""Read-only Helius getAccountInfo adapter for verified SPL mint decimals."""

from __future__ import annotations

import base64
import binascii
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from bangzen_prime.core.errors import DomainError, ExternalServiceError
from bangzen_prime.data.mint_metadata import (
    REJECTED,
    SUPPORTED_TOKEN_PROGRAMS,
    UNAVAILABLE,
    VERIFIED,
    MintMetadataEvidence,
)
from bangzen_prime.discovery.tokens import validate_mint

SERVICE = "helius_getAccountInfo"
_TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
_TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
_ADDRESS_RE = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")
_MINT_BASE_SIZE = 82
_DECIMALS_OFFSET = 44
_INITIALIZED_OFFSET = 45


class HeliusMintMetadataMalformed(ExternalServiceError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Helius mint account response malformed: {detail}",
            service=SERVICE,
            retryable=False,
        )


def _decode_address(address: str) -> bytes:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    for char in address:
        digit = alphabet.find(char)
        if digit < 0:
            raise ValueError("invalid base58")
        number = number * 58 + digit
    decoded = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return (b"\\x00" * (len(address) - len(address.lstrip("1")))) + decoded


class HeliusMintMetadataReader:
    """Validate owner, account layout, initialization and decimals before VERIFIED.

    account_info is an injected read-only RPC callable. The adapter deliberately does
    not parse Token-2022 TLV extensions; it reports the unparsed trailing-data length so downstream
    safety analysis cannot mistake this decimals check for a full extension audit.
    """

    def __init__(
        self,
        *,
        account_info: Callable[[str], Any],
        clock: Callable[[], datetime],
    ) -> None:
        self._account_info = account_info
        self._clock = clock

    def read(self, mint: str) -> MintMetadataEvidence:
        validate_mint(mint)
        if not _ADDRESS_RE.fullmatch(mint):
            raise DomainError("invalid Solana mint address")
        try:
            if len(_decode_address(mint)) != 32:
                raise DomainError("invalid Solana mint address")
        except ValueError:
            raise DomainError("invalid Solana mint address") from None

        observed_at = self._clock()
        if not isinstance(observed_at, datetime) or observed_at.tzinfo is None:
            raise DomainError("clock must return a timezone-aware datetime")
        result = self._account_info(mint)
        if not isinstance(result, dict):
            raise HeliusMintMetadataMalformed("getAccountInfo result must be an object")
        context = result.get("context")
        if not isinstance(context, dict):
            raise HeliusMintMetadataMalformed("RPC context missing")
        slot = context.get("slot")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise HeliusMintMetadataMalformed("RPC context slot missing or invalid")
        value = result.get("value")
        if value is None:
            return MintMetadataEvidence(
                mint=mint,
                validation_status=UNAVAILABLE,
                observed_at=observed_at,
                source=SERVICE,
                slot=slot,
                reason_codes=("MINT_ACCOUNT_NOT_FOUND",),
            )
        if not isinstance(value, dict):
            raise HeliusMintMetadataMalformed("account value must be an object")

        owner = value.get("owner")
        if not isinstance(owner, str) or owner not in SUPPORTED_TOKEN_PROGRAMS:
            return MintMetadataEvidence(
                mint=mint,
                validation_status=REJECTED,
                observed_at=observed_at,
                source=SERVICE,
                slot=slot,
                token_program=owner if isinstance(owner, str) else None,
                reason_codes=("UNSUPPORTED_MINT_OWNER_PROGRAM",),
            )
        if value.get("executable") is not False:
            return MintMetadataEvidence(
                mint=mint,
                validation_status=REJECTED,
                observed_at=observed_at,
                source=SERVICE,
                slot=slot,
                token_program=owner,
                reason_codes=("MINT_ACCOUNT_MUST_NOT_BE_EXECUTABLE",),
            )

        data = value.get("data")
        if (
            not isinstance(data, (list, tuple))
            or len(data) != 2
            or data[1] != "base64"
            or not isinstance(data[0], str)
        ):
            raise HeliusMintMetadataMalformed("account data must be a base64 tuple")
        try:
            raw = base64.b64decode(data[0], validate=True)
        except (binascii.Error, ValueError):
            raise HeliusMintMetadataMalformed(
                "account data is not valid base64"
            ) from None
        space = value.get("space")
        if space is not None and (
            isinstance(space, bool) or not isinstance(space, int) or space != len(raw)
        ):
            raise HeliusMintMetadataMalformed(
                "account space does not match decoded data"
            )
        if owner == _TOKEN_PROGRAM and len(raw) != _MINT_BASE_SIZE:
            raise HeliusMintMetadataMalformed(
                "classic Token Program mint must be exactly 82 bytes"
            )
        additional_data_length = 0
        if owner == _TOKEN_2022_PROGRAM:
            if len(raw) < _MINT_BASE_SIZE:
                raise HeliusMintMetadataMalformed(
                    "Token-2022 mint is shorter than its base layout"
                )
            if len(raw) > _MINT_BASE_SIZE:
                if len(raw) < 166 or len(raw) == 355:
                    raise HeliusMintMetadataMalformed(
                        "Token-2022 extended mint layout has an invalid size"
                    )
                if raw[82:165] != bytes(83):
                    raise HeliusMintMetadataMalformed(
                        "Token-2022 mint padding is invalid"
                    )
                if raw[165] != 1:
                    return MintMetadataEvidence(
                        mint=mint,
                        validation_status=REJECTED,
                        observed_at=observed_at,
                        source=SERVICE,
                        slot=slot,
                        token_program=owner,
                        account_data_length=len(raw),
                        reason_codes=("TOKEN_2022_ACCOUNT_IS_NOT_MINT",),
                    )
                additional_data_length = len(raw) - 166
        if len(raw) < _MINT_BASE_SIZE:
            raise HeliusMintMetadataMalformed("mint account data is truncated")

        initialized = raw[_INITIALIZED_OFFSET]
        if initialized not in (0, 1):
            raise HeliusMintMetadataMalformed("mint initialized flag is invalid")
        if initialized != 1:
            return MintMetadataEvidence(
                mint=mint,
                validation_status=REJECTED,
                observed_at=observed_at,
                source=SERVICE,
                slot=slot,
                token_program=owner,
                account_data_length=len(raw),
                additional_data_length=additional_data_length,
                reason_codes=("MINT_NOT_INITIALIZED",),
            )
        supply = int.from_bytes(raw[36:44], "little", signed=False)
        decimals = raw[_DECIMALS_OFFSET]
        return MintMetadataEvidence(
            mint=mint,
            validation_status=VERIFIED,
            observed_at=observed_at,
            source=SERVICE,
            slot=slot,
            token_program=owner,
            decimals=decimals,
            supply_raw=supply,
            is_initialized=True,
            account_data_length=len(raw),
            additional_data_length=additional_data_length,
        )
