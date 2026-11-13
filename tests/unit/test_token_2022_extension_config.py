import struct
import unittest

from bangzen_prime.domain.token_2022_extension_config import (
    decode_token_2022_extension_configurations,
)
from bangzen_prime.domain.token_2022_extensions import PARTIAL, REJECTED, VERIFIED
from bangzen_prime.errors import DomainError

_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _key(byte):
    return bytes([byte]) * 32


def _tlv(type_id, value):
    return type_id.to_bytes(2, "little") + len(value).to_bytes(2, "little") + value


def _base58(raw):
    zeros = len(raw) - len(raw.lstrip(b"\x00"))
    number = int.from_bytes(raw, "big")
    encoded = ""
    while number:
        number, rem = divmod(number, 58)
        encoded = _B58[rem] + encoded
    return "1" * zeros + encoded


class Token2022ConfigurationDecoderTests(unittest.TestCase):
    def test_decodes_transfer_fee_authorities_and_both_schedules(self):
        older = (
            (10).to_bytes(8, "little")
            + (500).to_bytes(8, "little")
            + (250).to_bytes(2, "little")
        )
        newer = (
            (12).to_bytes(8, "little")
            + (700).to_bytes(8, "little")
            + (500).to_bytes(2, "little")
        )
        value = _key(1) + _key(2) + (3).to_bytes(8, "little") + older + newer
        parsed = decode_token_2022_extension_configurations(_tlv(1, value))
        self.assertEqual(parsed.validation_status, VERIFIED)
        config = parsed.configurations[0]
        self.assertEqual(config.authorities[0][1], _base58(_key(1)))
        self.assertEqual(config.authorities[1][1], _base58(_key(2)))
        params = dict(config.parameters)
        self.assertEqual(params["withheld_amount"], 3)
        self.assertEqual(params["older_transfer_fee_basis_points"], 250)
        self.assertEqual(params["newer_transfer_fee_basis_points"], 500)
        self.assertEqual(params["newer_transfer_fee_epoch"], 12)
        self.assertIn("TRANSFER_FEE_NONZERO", config.risk_flags)

    def test_decodes_non_transferable_presence(self):
        parsed = decode_token_2022_extension_configurations(_tlv(9, b""))
        self.assertEqual(parsed.validation_status, VERIFIED)
        self.assertIn("NON_TRANSFERABLE", parsed.risk_flags)

    def test_decodes_metadata_pointer_authority_and_target(self):
        parsed = decode_token_2022_extension_configurations(
            _tlv(18, _key(7) + _key(8))
        )
        self.assertEqual(parsed.configurations[0].authorities[0][1], _base58(_key(7)))
        self.assertEqual(parsed.configurations[0].authorities[1][1], _base58(_key(8)))

    def test_zero_pubkey_is_none(self):
        parsed = decode_token_2022_extension_configurations(_tlv(12, bytes(32)))
        self.assertEqual(
            parsed.configurations[0].authorities,
            (("permanent_delegate", None),),
        )

    def test_decodes_transfer_hook_authority_and_program(self):
        parsed = decode_token_2022_extension_configurations(
            _tlv(14, _key(3) + _key(4))
        )
        config = parsed.configurations[0]
        self.assertEqual(config.authorities[0][1], _base58(_key(3)))
        self.assertEqual(config.authorities[1][1], _base58(_key(4)))
        self.assertIn("TRANSFER_HOOK_PROGRAM_CONFIGURED", config.risk_flags)

    def test_decodes_pausable_state(self):
        parsed = decode_token_2022_extension_configurations(
            _tlv(26, _key(5) + b"\x01")
        )
        config = parsed.configurations[0]
        self.assertEqual(dict(config.parameters)["paused"], True)
        self.assertIn("TOKEN_TRANSFERS_PAUSED", config.risk_flags)

    def test_decodes_frozen_default_account_state(self):
        parsed = decode_token_2022_extension_configurations(_tlv(6, b"\x02"))
        self.assertEqual(
            dict(parsed.configurations[0].parameters)["default_account_state"],
            "FROZEN",
        )
        self.assertIn("DEFAULT_ACCOUNTS_FROZEN", parsed.risk_flags)

    def test_decodes_interest_bearing_configuration(self):
        value = (
            bytes(32)
            + (100).to_bytes(8, "little", signed=True)
            + (-2).to_bytes(2, "little", signed=True)
            + (200).to_bytes(8, "little", signed=True)
            + (5).to_bytes(2, "little", signed=True)
        )
        parsed = decode_token_2022_extension_configurations(_tlv(10, value))
        params = dict(parsed.configurations[0].parameters)
        self.assertEqual(params["current_rate_bps"], 5)
        self.assertEqual(params["initialization_timestamp"], 100)

    def test_decodes_scaled_ui_amount_and_rejects_non_finite_multiplier(self):
        value = bytes(32) + struct.pack("<dqd", 1.5, 1000, 2.0)
        parsed = decode_token_2022_extension_configurations(_tlv(25, value))
        self.assertEqual(dict(parsed.configurations[0].parameters)["multiplier"], 1.5)
        invalid = bytes(32) + struct.pack("<dqd", float("nan"), 1000, 2.0)
        self.assertEqual(
            decode_token_2022_extension_configurations(_tlv(25, invalid)).validation_status,
            REJECTED,
        )

    def test_decodes_permissioned_burn_authority(self):
        parsed = decode_token_2022_extension_configurations(_tlv(28, _key(6)))
        self.assertEqual(
            parsed.configurations[0].authorities[0][1],
            _base58(_key(6)),
        )

    def test_unsupported_known_extension_is_partial_not_verified(self):
        parsed = decode_token_2022_extension_configurations(_tlv(4, bytes(295)))
        self.assertEqual(parsed.validation_status, PARTIAL)
        self.assertEqual(parsed.unsupported_extension_ids, (4,))

    def test_rejects_bad_lengths_and_fee_rates(self):
        self.assertEqual(
            decode_token_2022_extension_configurations(_tlv(14, bytes(63))).validation_status,
            REJECTED,
        )
        value = (
            bytes(64)
            + bytes(8)
            + bytes(16)
            + (10001).to_bytes(2, "little")
            + bytes(18)
        )
        self.assertEqual(
            decode_token_2022_extension_configurations(_tlv(1, value)).validation_status,
            REJECTED,
        )

    def test_rejects_invalid_default_state_and_pausable_flag(self):
        self.assertEqual(
            decode_token_2022_extension_configurations(_tlv(6, b"\x03")).validation_status,
            REJECTED,
        )
        self.assertEqual(
            decode_token_2022_extension_configurations(
                _tlv(26, bytes(32) + b"\x02")
            ).validation_status,
            REJECTED,
        )

    def test_rejects_duplicate_and_account_only_extensions(self):
        self.assertEqual(
            decode_token_2022_extension_configurations(
                _tlv(12, bytes(32)) + _tlv(12, bytes(32))
            ).validation_status,
            REJECTED,
        )
        self.assertEqual(
            decode_token_2022_extension_configurations(_tlv(15, b"\x01")).validation_status,
            REJECTED,
        )

    def test_empty_and_non_bytes_are_not_verified(self):
        self.assertEqual(
            decode_token_2022_extension_configurations(b"").validation_status,
            PARTIAL,
        )
        with self.assertRaises(DomainError):
            decode_token_2022_extension_configurations("bad")


if __name__ == "__main__":
    unittest.main()
