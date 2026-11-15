"""Read-only Helius reader for mint-owner classification and Token-2022 extension evidence."""

from __future__ import annotations

import base64
import binascii
from collections.abc import Callable
from datetime import datetime
from typing import Any

from bangzen_prime.core.errors import DomainError, ExternalServiceError
from bangzen_prime.discovery.tokens import validate_mint
from bangzen_prime.security.token_2022_extension_config import (
    ParsedToken2022Configuration,
    decode_token_2022_extension_configurations,
)
from bangzen_prime.security.token_2022_extension_evidence import (
    UNAVAILABLE,
    Token2022ExtensionEvidence,
)
from bangzen_prime.security.token_2022_extensions import (
    PARTIAL,
    REJECTED,
    VERIFIED,
    ParsedToken2022Extensions,
    Token2022ExtensionRecord,
    parse_token_2022_tlv,
)
from bangzen_prime.security.token_programs import TOKEN_PROGRAM_ID

SERVICE = "helius_token_2022_extensions"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"
_MINT_BASE_SIZE = 82
_EXTENDED_MINT_HEADER_SIZE = 166


class HeliusToken2022ExtensionMalformed(ExternalServiceError):
    def __init__(self, detail: str) -> None:
        super().__init__(
            f"Helius Token-2022 extension response malformed: {detail}",
            service=SERVICE,
            retryable=False,
        )


def _decode_base58_address(address: str) -> bytes:
    alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
    number = 0
    for char in address:
        digit = alphabet.find(char)
        if digit < 0:
            raise ValueError("invalid base58")
        number = number * 58 + digit
    decoded = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    return (b"\x00" * (len(address) - len(address.lstrip("1")))) + decoded


class HeliusToken2022ExtensionReader:
    """Fetch finalized mint state and decode Token-2022 TLV extension configurations.

    account_info is the injected read-only Helius getAccountInfo callable. The reader
    never interprets an extension's authority bytes or claims the mint is safe.
    """

    def __init__(
        self,
        *,
        account_info: Callable[[str], Any],
        clock: Callable[[], datetime],
    ) -> None:
        if not callable(account_info) or not callable(clock):
            raise DomainError("account_info and clock callables are required")
        self._account_info = account_info
        self._clock = clock

    def read(self, mint: str) -> Token2022ExtensionEvidence:
        validate_mint(mint)
        try:
            if len(_decode_base58_address(mint)) != 32:
                raise DomainError("invalid Solana mint address")
        except ValueError:
            raise DomainError("invalid Solana mint address") from None

        observed_at = self._clock()
        if (
            not isinstance(observed_at, datetime)
            or observed_at.tzinfo is None
            or observed_at.utcoffset() is None
        ):
            raise DomainError("clock must return a timezone-aware datetime")

        result = self._account_info(mint)
        if not isinstance(result, dict):
            raise HeliusToken2022ExtensionMalformed(
                "getAccountInfo result must be an object"
            )
        context = result.get("context")
        if not isinstance(context, dict):
            raise HeliusToken2022ExtensionMalformed("RPC context missing")
        slot = context.get("slot")
        if isinstance(slot, bool) or not isinstance(slot, int) or slot < 0:
            raise HeliusToken2022ExtensionMalformed("RPC context slot is invalid")

        value = result.get("value")
        if value is None:
            return self._evidence(
                mint,
                observed_at,
                slot,
                UNAVAILABLE,
                reason_codes=("MINT_ACCOUNT_NOT_FOUND",),
            )
        if not isinstance(value, dict):
            raise HeliusToken2022ExtensionMalformed("account value must be an object")

        owner = value.get("owner")
        if owner not in {TOKEN_2022_PROGRAM, TOKEN_PROGRAM_ID}:
            return self._evidence(
                mint,
                observed_at,
                slot,
                REJECTED,
                token_program=owner if isinstance(owner, str) else None,
                reason_codes=("UNSUPPORTED_MINT_OWNER_PROGRAM",),
            )
        if value.get("executable") is not False:
            return self._evidence(
                mint,
                observed_at,
                slot,
                REJECTED,
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
            raise HeliusToken2022ExtensionMalformed(
                "account data must be a base64 tuple"
            )
        try:
            raw = base64.b64decode(data[0], validate=True)
        except (binascii.Error, ValueError):
            raise HeliusToken2022ExtensionMalformed(
                "account data is not valid base64"
            ) from None

        space = value.get("space")
        if space is not None and (
            isinstance(space, bool) or not isinstance(space, int) or space != len(raw)
        ):
            raise HeliusToken2022ExtensionMalformed(
                "account space does not match decoded data"
            )

        # Confirm classic SPL Token accounts are actual initialized 82-byte Mint layouts.
        if owner == TOKEN_PROGRAM_ID:
            if len(raw) != _MINT_BASE_SIZE:
                return self._evidence(
                    mint,
                    observed_at,
                    slot,
                    REJECTED,
                    token_program=owner,
                    account_data_length=len(raw),
                    reason_codes=("TOKEN_PROGRAM_ACCOUNT_NOT_MINT",),
                )
            if raw[45] not in (0, 1):
                raise HeliusToken2022ExtensionMalformed(
                    "classic mint initialized flag is invalid"
                )
            if raw[45] != 1:
                return self._evidence(
                    mint,
                    observed_at,
                    slot,
                    REJECTED,
                    token_program=owner,
                    account_data_length=len(raw),
                    reason_codes=("MINT_NOT_INITIALIZED",),
                )
            mint_authority_tag = int.from_bytes(raw[0:4], "little")
            freeze_authority_tag = int.from_bytes(raw[46:50], "little")
            if mint_authority_tag not in (0, 1) or freeze_authority_tag not in (0, 1):
                return self._evidence(
                    mint,
                    observed_at,
                    slot,
                    REJECTED,
                    token_program=owner,
                    account_data_length=len(raw),
                    reason_codes=("CLASSIC_SPL_MINT_LAYOUT_INVALID",),
                )
            return self._evidence(
                mint,
                observed_at,
                slot,
                REJECTED,
                token_program=owner,
                account_data_length=len(raw),
                reason_codes=("CLASSIC_SPL_MINT_CONFIRMED",),
            )

        if len(raw) < _MINT_BASE_SIZE:
            raise HeliusToken2022ExtensionMalformed(
                "Token-2022 mint is shorter than base layout"
            )
        if raw[45] not in (0, 1):
            raise HeliusToken2022ExtensionMalformed("mint initialized flag is invalid")
        if raw[45] != 1:
            return self._evidence(
                mint,
                observed_at,
                slot,
                REJECTED,
                token_program=owner,
                account_data_length=len(raw),
                reason_codes=("MINT_NOT_INITIALIZED",),
            )

        if len(raw) == _MINT_BASE_SIZE:
            parsed = ParsedToken2022Extensions(
                VERIFIED, (), (), (), ("NO_EXTENSIONS_PRESENT",)
            )
            config = ParsedToken2022Configuration(
                VERIFIED, (), (), (), ("NO_EXTENSIONS_PRESENT",)
            )
        else:
            if len(raw) < _EXTENDED_MINT_HEADER_SIZE or len(raw) == 355:
                raise HeliusToken2022ExtensionMalformed(
                    "extended mint layout has invalid size"
                )
            if raw[82:165] != bytes(83):
                raise HeliusToken2022ExtensionMalformed(
                    "Token-2022 mint padding is invalid"
                )
            if raw[165] != 1:
                return self._evidence(
                    mint,
                    observed_at,
                    slot,
                    REJECTED,
                    token_program=owner,
                    account_data_length=len(raw),
                    reason_codes=("TOKEN_2022_ACCOUNT_IS_NOT_MINT",),
                )
            tlv_data = raw[_EXTENDED_MINT_HEADER_SIZE:]
            parsed = parse_token_2022_tlv(tlv_data)
            config = decode_token_2022_extension_configurations(tlv_data)

        status = (
            REJECTED
            if parsed.validation_status == REJECTED
            or config.validation_status == REJECTED
            else (
                PARTIAL
                if parsed.validation_status == PARTIAL
                or config.validation_status == PARTIAL
                else VERIFIED
            )
        )
        return self._evidence(
            mint,
            observed_at,
            slot,
            status,
            token_program=owner,
            account_data_length=len(raw),
            extensions=parsed.extensions,
            risk_flags=tuple(dict.fromkeys(parsed.risk_flags + config.risk_flags)),
            unknown_extension_ids=parsed.unknown_extension_ids,
            reason_codes=tuple(
                dict.fromkeys(parsed.reason_codes + config.reason_codes)
            ),
            configuration=config,
        )

    @staticmethod
    def _evidence(
        mint: str,
        observed_at: datetime,
        slot: int,
        status: str,
        *,
        token_program: str | None = None,
        account_data_length: int | None = None,
        extensions: tuple[Token2022ExtensionRecord, ...] = (),
        risk_flags: tuple[str, ...] = (),
        unknown_extension_ids: tuple[int, ...] = (),
        reason_codes: tuple[str, ...] = (),
        configuration: ParsedToken2022Configuration | None = None,
    ) -> Token2022ExtensionEvidence:
        return Token2022ExtensionEvidence(
            mint=mint,
            validation_status=status,
            observed_at=observed_at,
            source=SERVICE,
            source_record_id=f"{mint}:{slot}:{account_data_length if account_data_length is not None else 'NO_DATA'}",
            slot=slot,
            token_program=token_program,
            account_data_length=account_data_length,
            extensions=extensions,
            risk_flags=risk_flags,
            unknown_extension_ids=unknown_extension_ids,
            reason_codes=reason_codes,
            configuration=configuration,
        )
