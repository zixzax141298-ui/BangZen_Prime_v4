import base64
import unittest
from datetime import UTC, datetime

from bangzen_prime.domain.mint_metadata import REJECTED, UNAVAILABLE, VERIFIED
from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.adapters.chain.helius_mint_metadata import (
    HeliusMintMetadataMalformed,
    HeliusMintMetadataReader,
)
from tests.support import SOL_MINT

NOW = datetime(2026, 11, 13, 4, 0, tzinfo=UTC)
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


def account_data(*, decimals=9, initialized=1, supply=123456, length=82):
    raw = bytearray(length)
    raw[36:44] = supply.to_bytes(8, "little")
    raw[44] = decimals
    raw[45] = initialized
    if length > 165:
        raw[165] = 1
    return bytes(raw)


def rpc_result(*, owner=TOKEN_PROGRAM, raw=None, slot=500, executable=False):
    raw = account_data() if raw is None else raw
    return {
        "context": {"slot": slot},
        "value": {
            "owner": owner,
            "executable": executable,
            "data": [base64.b64encode(raw).decode("ascii"), "base64"],
            "space": len(raw),
        },
    }


class HeliusMintMetadataReaderTests(unittest.TestCase):
    def reader(self, payload):
        calls = []

        def account_info(address):
            calls.append(address)
            return payload

        reader = HeliusMintMetadataReader(account_info=account_info, clock=lambda: NOW)
        return reader, calls

    def test_verifies_classic_token_program_mint(self):
        reader, calls = self.reader(rpc_result())
        evidence = reader.read(SOL_MINT)
        self.assertEqual(calls, [SOL_MINT])
        self.assertEqual(evidence.validation_status, VERIFIED)
        self.assertEqual(evidence.decimals, 9)
        self.assertEqual(evidence.supply_raw, 123456)
        self.assertTrue(evidence.is_initialized)
        self.assertEqual(evidence.slot, 500)
        self.assertEqual(evidence.to_verified_decimals().decimals, 9)

    def test_verifies_token_2022_base_mint_and_reports_additional_data_length(self):
        raw = account_data(decimals=6, length=200)
        reader, _ = self.reader(rpc_result(owner=TOKEN_2022_PROGRAM, raw=raw))
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, VERIFIED)
        self.assertEqual(evidence.decimals, 6)
        self.assertEqual(evidence.additional_data_length, 34)

    def test_missing_account_is_unavailable_not_zero_or_verified(self):
        reader, _ = self.reader({"context": {"slot": 501}, "value": None})
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, UNAVAILABLE)
        self.assertIsNone(evidence.decimals)
        with self.assertRaises(DomainError):
            evidence.to_verified_decimals()

    def test_unknown_owner_is_rejected(self):
        reader, _ = self.reader(rpc_result(owner="11111111111111111111111111111111"))
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, REJECTED)
        self.assertIsNone(evidence.decimals)

    def test_executable_account_is_rejected(self):
        reader, _ = self.reader(rpc_result(executable=True))
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, REJECTED)
        self.assertIsNone(evidence.decimals)

    def test_non_string_owner_is_rejected_without_type_error(self):
        reader, _ = self.reader(rpc_result(owner=["unexpected"]))
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, REJECTED)

    def test_uninitialized_mint_is_rejected(self):
        reader, _ = self.reader(rpc_result(raw=account_data(initialized=0)))
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, REJECTED)
        self.assertEqual(evidence.reason_codes, ("MINT_NOT_INITIALIZED",))

    def test_classic_mint_requires_exact_base_layout(self):
        reader, _ = self.reader(rpc_result(raw=account_data(length=83)))
        with self.assertRaises(HeliusMintMetadataMalformed):
            reader.read(SOL_MINT)

    def test_token_2022_rejects_token_account_discriminator(self):
        raw = bytearray(account_data(length=200))
        raw[165] = 2
        reader, _ = self.reader(rpc_result(owner=TOKEN_2022_PROGRAM, raw=bytes(raw)))
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, REJECTED)
        self.assertEqual(evidence.reason_codes, ("TOKEN_2022_ACCOUNT_IS_NOT_MINT",))

    def test_token_2022_rejects_nonzero_mint_padding(self):
        raw = bytearray(account_data(length=200))
        raw[100] = 1
        reader, _ = self.reader(rpc_result(owner=TOKEN_2022_PROGRAM, raw=bytes(raw)))
        with self.assertRaises(HeliusMintMetadataMalformed):
            reader.read(SOL_MINT)

    def test_token_2022_rejects_token_account_base_length(self):
        reader, _ = self.reader(
            rpc_result(owner=TOKEN_2022_PROGRAM, raw=account_data(length=165))
        )
        with self.assertRaises(HeliusMintMetadataMalformed):
            reader.read(SOL_MINT)

    def test_token_2022_rejects_truncated_base_layout(self):
        reader, _ = self.reader(
            rpc_result(owner=TOKEN_2022_PROGRAM, raw=account_data(length=81))
        )
        with self.assertRaises(HeliusMintMetadataMalformed):
            reader.read(SOL_MINT)

    def test_rejects_bad_space_and_base64(self):
        payload = rpc_result()
        payload["value"]["space"] = 81
        reader, _ = self.reader(payload)
        with self.assertRaises(HeliusMintMetadataMalformed):
            reader.read(SOL_MINT)

        payload = rpc_result()
        payload["value"]["data"] = ["%%%not-base64%%%", "base64"]
        reader, _ = self.reader(payload)
        with self.assertRaises(HeliusMintMetadataMalformed):
            reader.read(SOL_MINT)

    def test_rejects_missing_or_invalid_rpc_slot(self):
        reader, _ = self.reader({"context": {"slot": -1}, "value": None})
        with self.assertRaises(HeliusMintMetadataMalformed):
            reader.read(SOL_MINT)

    def test_rejects_invalid_mint_address_before_rpc(self):
        reader, calls = self.reader(rpc_result())
        with self.assertRaises(DomainError):
            reader.read("not-a-mint")
        self.assertEqual(calls, [])

    def test_rejects_naive_clock(self):
        reader = HeliusMintMetadataReader(
            account_info=lambda _address: rpc_result(),
            clock=lambda: datetime(2026, 11, 13),
        )
        with self.assertRaises(DomainError):
            reader.read(SOL_MINT)


if __name__ == "__main__":
    unittest.main()
