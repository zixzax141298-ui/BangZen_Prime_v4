"""Fail-closed decoder for selected Token-2022 mint extension configurations.

Layouts are pinned to the SPL Token-2022 interface structures documented in
docs/TOKEN_2022_CONFIG_AUTHORITY_AUDIT.md. Unknown or unsupported structures remain
PARTIAL; malformed fixed-width layouts are REJECTED. This is evidence, not policy.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass

from bangzen_prime.core.errors import DomainError
from bangzen_prime.security.token_2022_extensions import PARTIAL, REJECTED, VERIFIED

# SPL Token-2022 ExtensionType discriminants with fixed layouts decoded here.
_LAYOUTS = {
    1: 108,  # TransferFeeConfig
    3: 32,  # MintCloseAuthority
    6: 1,  # DefaultAccountState
    9: 0,  # NonTransferable
    10: 52,  # InterestBearingConfig
    12: 32,  # PermanentDelegate
    14: 64,  # TransferHook
    18: 64,  # MetadataPointer
    20: 64,  # GroupPointer
    22: 64,  # GroupMemberPointer
    25: 56,  # ScaledUiAmountConfig
    26: 33,  # PausableConfig
    28: 32,  # PermissionedBurnConfig
}

_NAMES = {
    1: "TRANSFER_FEE_CONFIG",
    3: "MINT_CLOSE_AUTHORITY",
    6: "DEFAULT_ACCOUNT_STATE",
    9: "NON_TRANSFERABLE",
    10: "INTEREST_BEARING_CONFIG",
    12: "PERMANENT_DELEGATE",
    14: "TRANSFER_HOOK",
    18: "METADATA_POINTER",
    20: "GROUP_POINTER",
    22: "GROUP_MEMBER_POINTER",
    25: "SCALED_UI_AMOUNT",
    26: "PAUSABLE",
    28: "PERMISSIONED_BURN",
}
_ACCOUNT_ONLY_IDS = frozenset({2, 5, 7, 8, 11, 13, 15, 17, 27})
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


@dataclass(frozen=True)
class Token2022ExtensionConfiguration:
    type_id: int
    name: str
    authorities: tuple[tuple[str, str | None], ...] = ()
    parameters: tuple[tuple[str, int | float | bool | str], ...] = ()
    risk_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class ParsedToken2022Configuration:
    validation_status: str
    configurations: tuple[Token2022ExtensionConfiguration, ...]
    unsupported_extension_ids: tuple[int, ...]
    risk_flags: tuple[str, ...]
    reason_codes: tuple[str, ...]


def _base58_encode(raw: bytes) -> str:
    zeros = len(raw) - len(raw.lstrip(b"\x00"))
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, remainder = divmod(number, 58)
        encoded = _B58[remainder] + encoded
    return ("1" * zeros) + encoded


def _optional_pubkey(raw: bytes) -> str | None:
    if len(raw) != 32:
        raise DomainError("optional public key must be exactly 32 bytes")
    return None if not any(raw) else _base58_encode(raw)


def _u16(raw: bytes) -> int:
    return int.from_bytes(raw, "little")


def _u64(raw: bytes) -> int:
    return int.from_bytes(raw, "little")


def _i64(raw: bytes) -> int:
    return int.from_bytes(raw, "little", signed=True)


def _decode_one(type_id: int, value: bytes) -> Token2022ExtensionConfiguration:
    expected = _LAYOUTS[type_id]
    if len(value) != expected:
        raise DomainError(f"{_NAMES[type_id]} extension length must be {expected}")

    authorities: list[tuple[str, str | None]] = []
    parameters: list[tuple[str, int | float | bool | str]] = []
    flags: list[str] = []

    if type_id == 1:
        authorities.extend(
            (
                ("transfer_fee_config_authority", _optional_pubkey(value[0:32])),
                ("withdraw_withheld_authority", _optional_pubkey(value[32:64])),
            )
        )
        parameters.append(("withheld_amount", _u64(value[64:72])))
        for label, start in (("older", 72), ("newer", 90)):
            epoch = _u64(value[start : start + 8])
            maximum_fee = _u64(value[start + 8 : start + 16])
            basis_points = _u16(value[start + 16 : start + 18])
            if basis_points > 10_000:
                raise DomainError("transfer fee basis points exceed 10000")
            parameters.extend(
                (
                    (f"{label}_transfer_fee_epoch", epoch),
                    (f"{label}_transfer_fee_maximum_fee", maximum_fee),
                    (f"{label}_transfer_fee_basis_points", basis_points),
                )
            )
        if authorities[0][1] is not None:
            flags.append("TRANSFER_FEE_CONFIG_AUTHORITY_PRESENT")
        if authorities[1][1] is not None:
            flags.append("TRANSFER_FEE_WITHDRAW_AUTHORITY_PRESENT")
        if any(
            dict(parameters).get(f"{label}_transfer_fee_basis_points", 0) > 0
            and dict(parameters).get(f"{label}_transfer_fee_maximum_fee", 0) > 0
            for label in ("older", "newer")
        ):
            flags.append("TRANSFER_FEE_NONZERO")

    elif type_id == 3:
        authorities.append(("mint_close_authority", _optional_pubkey(value)))
        if authorities[0][1] is not None:
            flags.append("MINT_CLOSE_AUTHORITY_ACTIVE")

    elif type_id == 6:
        state = value[0]
        if state not in (0, 1, 2):
            raise DomainError("default account state is invalid")
        parameters.append(
            (
                "default_account_state",
                {0: "UNINITIALIZED", 1: "INITIALIZED", 2: "FROZEN"}[state],
            )
        )
        if state == 2:
            flags.append("DEFAULT_ACCOUNTS_FROZEN")
        elif state == 0:
            flags.append("DEFAULT_ACCOUNTS_UNINITIALIZED")

    elif type_id == 9:
        flags.append("NON_TRANSFERABLE")

    elif type_id == 10:
        authorities.append(("interest_rate_authority", _optional_pubkey(value[0:32])))
        parameters.extend(
            (
                ("initialization_timestamp", _i64(value[32:40])),
                (
                    "pre_update_average_rate_bps",
                    int.from_bytes(value[40:42], "little", signed=True),
                ),
                ("last_update_timestamp", _i64(value[42:50])),
                (
                    "current_rate_bps",
                    int.from_bytes(value[50:52], "little", signed=True),
                ),
            )
        )
        if authorities[0][1] is not None:
            flags.append("INTEREST_RATE_AUTHORITY_PRESENT")

    elif type_id == 12:
        authorities.append(("permanent_delegate", _optional_pubkey(value)))
        if authorities[0][1] is not None:
            flags.append("PERMANENT_DELEGATE_ACTIVE")

    elif type_id == 14:
        authorities.extend(
            (
                ("transfer_hook_authority", _optional_pubkey(value[0:32])),
                ("transfer_hook_program_id", _optional_pubkey(value[32:64])),
            )
        )
        if authorities[0][1] is not None:
            flags.append("TRANSFER_HOOK_AUTHORITY_PRESENT")
        if authorities[1][1] is not None:
            flags.append("TRANSFER_HOOK_PROGRAM_CONFIGURED")

    elif type_id in (18, 20, 22):
        first_name, second_name = {
            18: ("metadata_pointer_authority", "metadata_address"),
            20: ("group_pointer_authority", "group_address"),
            22: ("group_member_pointer_authority", "member_address"),
        }[type_id]
        authorities.extend(
            (
                (first_name, _optional_pubkey(value[0:32])),
                (second_name, _optional_pubkey(value[32:64])),
            )
        )
        if authorities[0][1] is not None:
            flags.append(f"{_NAMES[type_id]}_AUTHORITY_PRESENT")
        if authorities[1][1] is not None:
            flags.append(f"{_NAMES[type_id]}_ADDRESS_CONFIGURED")

    elif type_id == 25:
        authorities.append(
            ("scaled_ui_amount_authority", _optional_pubkey(value[0:32]))
        )
        multiplier = struct.unpack("<d", value[32:40])[0]
        effective_at = _i64(value[40:48])
        new_multiplier = struct.unpack("<d", value[48:56])[0]
        if not math.isfinite(multiplier) or multiplier <= 0:
            raise DomainError("scaled UI multiplier must be finite and positive")
        if not math.isfinite(new_multiplier) or new_multiplier <= 0:
            raise DomainError("new scaled UI multiplier must be finite and positive")
        parameters.extend(
            (
                ("multiplier", multiplier),
                ("new_multiplier_effective_timestamp", effective_at),
                ("new_multiplier", new_multiplier),
            )
        )
        if authorities[0][1] is not None:
            flags.append("SCALED_UI_AMOUNT_AUTHORITY_PRESENT")

    elif type_id == 26:
        authorities.append(("pausable_authority", _optional_pubkey(value[0:32])))
        if value[32] not in (0, 1):
            raise DomainError("pausable flag must be zero or one")
        parameters.append(("paused", bool(value[32])))
        if value[32] == 1:
            flags.append("TOKEN_TRANSFERS_PAUSED")
        if authorities[0][1] is not None:
            flags.append("PAUSABLE_AUTHORITY_PRESENT")

    elif type_id == 28:
        authorities.append(("permissioned_burn_authority", _optional_pubkey(value)))
        if authorities[0][1] is not None:
            flags.append("PERMISSIONED_BURN_AUTHORITY_PRESENT")

    return Token2022ExtensionConfiguration(
        type_id=type_id,
        name=_NAMES[type_id],
        authorities=tuple(authorities),
        parameters=tuple(parameters),
        risk_flags=tuple(flags),
    )


def decode_token_2022_extension_configurations(
    tlv_data: bytes,
) -> ParsedToken2022Configuration:
    """Decode supported fixed-width mint extension values from a TLV region."""
    if not isinstance(tlv_data, bytes):
        raise DomainError("Token-2022 TLV data must be bytes")
    if not tlv_data or not any(tlv_data):
        return ParsedToken2022Configuration(
            PARTIAL, (), (), (), ("EMPTY_TLV_EXTENSION_REGION",)
        )

    configurations: list[Token2022ExtensionConfiguration] = []
    unsupported: list[int] = []
    risk_flags: list[str] = []
    reasons: list[str] = []
    seen: set[int] = set()
    offset = 0

    while offset < len(tlv_data):
        remaining = tlv_data[offset:]
        if not any(remaining):
            break
        if len(remaining) < 4:
            return ParsedToken2022Configuration(
                REJECTED,
                tuple(configurations),
                tuple(unsupported),
                tuple(dict.fromkeys(risk_flags)),
                ("TRUNCATED_TLV_HEADER",),
            )
        type_id = _u16(remaining[0:2])
        value_length = _u16(remaining[2:4])
        if type_id == 0:
            if value_length == 0 and not any(remaining[4:]):
                break
            return ParsedToken2022Configuration(
                REJECTED,
                tuple(configurations),
                tuple(unsupported),
                tuple(dict.fromkeys(risk_flags)),
                ("INVALID_UNINITIALIZED_EXTENSION_ENTRY",),
            )
        if type_id in seen:
            return ParsedToken2022Configuration(
                REJECTED,
                tuple(configurations),
                tuple(unsupported),
                tuple(dict.fromkeys(risk_flags)),
                ("DUPLICATE_EXTENSION_TYPE",),
            )
        if type_id in _ACCOUNT_ONLY_IDS:
            return ParsedToken2022Configuration(
                REJECTED,
                tuple(configurations),
                tuple(unsupported),
                tuple(dict.fromkeys(risk_flags)),
                ("ACCOUNT_EXTENSION_FOUND_IN_MINT",),
            )
        end = 4 + value_length
        if end > len(remaining):
            return ParsedToken2022Configuration(
                REJECTED,
                tuple(configurations),
                tuple(unsupported),
                tuple(dict.fromkeys(risk_flags)),
                ("TLV_VALUE_EXCEEDS_ACCOUNT_DATA",),
            )
        value = remaining[4:end]
        seen.add(type_id)
        if type_id not in _NAMES:
            unsupported.append(type_id)
            reasons.append("UNSUPPORTED_EXTENSION_CONFIGURATION")
        else:
            try:
                decoded = _decode_one(type_id, value)
            except DomainError:
                return ParsedToken2022Configuration(
                    REJECTED,
                    tuple(configurations),
                    tuple(unsupported),
                    tuple(dict.fromkeys(risk_flags)),
                    ("MALFORMED_EXTENSION_CONFIGURATION",),
                )
            configurations.append(decoded)
            risk_flags.extend(decoded.risk_flags)
        offset += end

    status = PARTIAL if unsupported else VERIFIED
    if unsupported:
        risk_flags.append("UNSUPPORTED_EXTENSION_CONFIGURATION_PRESENT")
    return ParsedToken2022Configuration(
        status,
        tuple(configurations),
        tuple(unsupported),
        tuple(dict.fromkeys(risk_flags)),
        tuple(dict.fromkeys(reasons)),
    )
