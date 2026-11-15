"""Pure Token-2022 mint TLV parser and extension risk annotations.

The catalog mirrors Solana's published ExtensionType discriminants (u16 LE).
This parser validates TLV framing and identifies known mint extensions; it does
not deserialize extension authorities/configuration or declare a token safe.
Unknown IDs remain PARTIAL so catalog drift cannot silently become a clean audit.
"""

from __future__ import annotations

from dataclasses import dataclass

from bangzen_prime.core.errors import DomainError

VERIFIED = "VERIFIED"
PARTIAL = "PARTIAL"
REJECTED = "REJECTED"

# Published ExtensionType discriminants, pinned to the catalog revision documented
# in docs/TOKEN_2022_EXTENSION_AUDIT.md. Unknown future IDs are never assumed safe.
MINT_EXTENSION_NAMES = {
    1: "TRANSFER_FEE_CONFIG",
    3: "MINT_CLOSE_AUTHORITY",
    4: "CONFIDENTIAL_TRANSFER_MINT",
    6: "DEFAULT_ACCOUNT_STATE",
    9: "NON_TRANSFERABLE",
    10: "INTEREST_BEARING_CONFIG",
    12: "PERMANENT_DELEGATE",
    14: "TRANSFER_HOOK",
    16: "CONFIDENTIAL_TRANSFER_FEE_CONFIG",
    18: "METADATA_POINTER",
    19: "TOKEN_METADATA",
    20: "GROUP_POINTER",
    21: "TOKEN_GROUP",
    22: "GROUP_MEMBER_POINTER",
    23: "TOKEN_GROUP_MEMBER",
    24: "CONFIDENTIAL_MINT_BURN",
    25: "SCALED_UI_AMOUNT",
    26: "PAUSABLE",
    28: "PERMISSIONED_BURN",
}

# These discriminants describe token-account state, not mint state. Finding one in
# mint TLV is structurally inconsistent and must not be accepted as a valid audit.
ACCOUNT_ONLY_EXTENSION_IDS = frozenset({2, 5, 7, 8, 11, 13, 15, 17, 27})

RISK_FLAGS_BY_ID = {
    1: ("TRANSFER_FEE_CONFIG_PRESENT",),
    3: ("MINT_CLOSE_AUTHORITY_PRESENT",),
    4: ("CONFIDENTIAL_TRANSFER_PRESENT",),
    6: ("DEFAULT_ACCOUNT_STATE_PRESENT",),
    9: ("NON_TRANSFERABLE",),
    10: ("INTEREST_BEARING_PRESENT",),
    12: ("PERMANENT_DELEGATE_PRESENT",),
    14: ("TRANSFER_HOOK_PRESENT",),
    16: ("CONFIDENTIAL_TRANSFER_FEE_CONFIG_PRESENT",),
    18: ("METADATA_POINTER_PRESENT",),
    19: ("TOKEN_METADATA_PRESENT",),
    20: ("GROUP_POINTER_PRESENT",),
    21: ("TOKEN_GROUP_PRESENT",),
    22: ("GROUP_MEMBER_POINTER_PRESENT",),
    23: ("TOKEN_GROUP_MEMBER_PRESENT",),
    24: ("CONFIDENTIAL_MINT_BURN_PRESENT",),
    25: ("SCALED_UI_AMOUNT_PRESENT",),
    26: ("PAUSABLE_PRESENT",),
    28: ("PERMISSIONED_BURN_PRESENT",),
}


@dataclass(frozen=True)
class Token2022ExtensionRecord:
    type_id: int
    name: str
    value_length: int
    risk_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedToken2022Extensions:
    validation_status: str
    extensions: tuple[Token2022ExtensionRecord, ...]
    risk_flags: tuple[str, ...]
    unknown_extension_ids: tuple[int, ...]
    reason_codes: tuple[str, ...]


def parse_token_2022_tlv(tlv_data: bytes) -> ParsedToken2022Extensions:
    """Parse TLV headers without interpreting provider-controlled extension values.

    Layout: repeated u16 little-endian type, u16 little-endian value length, value.
    An all-zero tail is treated as allocation padding only after at least one
    extension; an entirely empty/zero TLV area is PARTIAL, not a clean bill of health.
    """
    if not isinstance(tlv_data, bytes):
        raise DomainError("Token-2022 TLV data must be bytes")

    if not tlv_data:
        return ParsedToken2022Extensions(
            PARTIAL, (), (), (), ("EMPTY_TLV_EXTENSION_REGION",)
        )

    records: list[Token2022ExtensionRecord] = []
    unknown: list[int] = []
    seen: set[int] = set()
    offset = 0
    reasons: list[str] = []

    while offset < len(tlv_data):
        remaining = tlv_data[offset:]
        if not any(remaining):
            if not records:
                return ParsedToken2022Extensions(
                    PARTIAL, (), (), (), ("EMPTY_TLV_EXTENSION_REGION",)
                )
            break
        if len(remaining) < 4:
            return ParsedToken2022Extensions(
                REJECTED,
                tuple(records),
                _unique_flags(records),
                tuple(unknown),
                ("TRUNCATED_TLV_HEADER",),
            )

        type_id = int.from_bytes(remaining[0:2], "little")
        value_length = int.from_bytes(remaining[2:4], "little")
        if type_id == 0:
            if value_length == 0 and not any(remaining[4:]):
                if not records:
                    return ParsedToken2022Extensions(
                        PARTIAL, (), (), (), ("EMPTY_TLV_EXTENSION_REGION",)
                    )
                break
            return ParsedToken2022Extensions(
                REJECTED,
                tuple(records),
                _unique_flags(records),
                tuple(unknown),
                ("INVALID_UNINITIALIZED_EXTENSION_ENTRY",),
            )

        if type_id in seen:
            return ParsedToken2022Extensions(
                REJECTED,
                tuple(records),
                _unique_flags(records),
                tuple(unknown),
                ("DUPLICATE_EXTENSION_TYPE",),
            )
        if type_id in ACCOUNT_ONLY_EXTENSION_IDS:
            return ParsedToken2022Extensions(
                REJECTED,
                tuple(records),
                _unique_flags(records),
                tuple(unknown),
                ("ACCOUNT_EXTENSION_FOUND_IN_MINT",),
            )

        end = 4 + value_length
        if end > len(remaining):
            return ParsedToken2022Extensions(
                REJECTED,
                tuple(records),
                _unique_flags(records),
                tuple(unknown),
                ("TLV_VALUE_EXCEEDS_ACCOUNT_DATA",),
            )

        name = MINT_EXTENSION_NAMES.get(type_id)
        flags = RISK_FLAGS_BY_ID.get(type_id, ())
        if name is None:
            name = "UNKNOWN_EXTENSION"
            unknown.append(type_id)
            reasons.append("UNKNOWN_EXTENSION_TYPE")
        records.append(Token2022ExtensionRecord(type_id, name, value_length, flags))
        seen.add(type_id)
        offset += end

    status = PARTIAL if unknown else VERIFIED
    flags = _unique_flags(records)
    if unknown:
        flags += ("UNKNOWN_EXTENSION_PRESENT",)
    return ParsedToken2022Extensions(
        status, tuple(records), flags, tuple(unknown), tuple(dict.fromkeys(reasons))
    )


def _unique_flags(records: list[Token2022ExtensionRecord]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(flag for record in records for flag in record.risk_flags)
    )
