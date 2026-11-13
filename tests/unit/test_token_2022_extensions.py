import base64
import unittest
from datetime import UTC, datetime

from bangzen_prime.domain.token_2022_extension_evidence import UNAVAILABLE
from bangzen_prime.domain.token_2022_extensions import (
    PARTIAL,
    REJECTED,
    VERIFIED,
    parse_token_2022_tlv,
)
from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.adapters.chain.helius_token_2022_extensions import (
    HeliusToken2022ExtensionMalformed,
    HeliusToken2022ExtensionReader,
)
from tests.support import SOL_MINT

NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)
TOKEN_PROGRAM = "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"
TOKEN_2022_PROGRAM = "TokenzQdBNbLqP5VEhdkAS6EPFLC1PHnBqCXEpPxuEb"


def tlv(type_id, value=b"\x01"):
    return type_id.to_bytes(2, "little") + len(value).to_bytes(2, "little") + value


def mint_data(extension_data=b"", *, initialized=1):
    raw = bytearray(166 + len(extension_data))
    raw[36:44] = (1234).to_bytes(8, "little")
    raw[44] = 6
    raw[45] = initialized
    raw[165] = 1
    raw[166:] = extension_data
    return bytes(raw)


def classic_mint_data(*, initialized=1):
    raw = bytearray(82)
    raw[36:44] = (1234).to_bytes(8, "little")
    raw[44] = 6
    raw[45] = initialized
    return bytes(raw)


def rpc_result(raw=None, *, owner=TOKEN_2022_PROGRAM, slot=900, executable=False):
    raw = mint_data(tlv(14, bytes(64))) if raw is None else raw
    return {
        "context": {"slot": slot},
        "value": {
            "owner": owner,
            "executable": executable,
            "data": [base64.b64encode(raw).decode("ascii"), "base64"],
            "space": len(raw),
        },
    }


class Token2022TlvParserTests(unittest.TestCase):
    def test_detects_known_extensions_and_risk_flags(self):
        parsed = parse_token_2022_tlv(
            tlv(1, bytes(108)) + tlv(12, bytes(32)) + tlv(14, bytes(64))
        )
        self.assertEqual(parsed.validation_status, VERIFIED)
        self.assertEqual(
            [item.name for item in parsed.extensions],
            ["TRANSFER_FEE_CONFIG", "PERMANENT_DELEGATE", "TRANSFER_HOOK"],
        )
        self.assertEqual(
            parsed.risk_flags,
            (
                "TRANSFER_FEE_CONFIG_PRESENT",
                "PERMANENT_DELEGATE_PRESENT",
                "TRANSFER_HOOK_PRESENT",
            ),
        )

    def test_unknown_extension_is_partial_not_safe(self):
        parsed = parse_token_2022_tlv(tlv(65000, b"opaque"))
        self.assertEqual(parsed.validation_status, PARTIAL)
        self.assertEqual(parsed.unknown_extension_ids, (65000,))
        self.assertIn("UNKNOWN_EXTENSION_PRESENT", parsed.risk_flags)

    def test_rejects_truncated_header_and_value(self):
        for raw in (b"\x01\x00", b"\x01\x00\x05\x00\x01"):
            self.assertEqual(parse_token_2022_tlv(raw).validation_status, REJECTED)

    def test_rejects_duplicate_extension(self):
        parsed = parse_token_2022_tlv(tlv(14, bytes(64)) + tlv(14, bytes(64)))
        self.assertEqual(parsed.validation_status, REJECTED)
        self.assertIn("DUPLICATE_EXTENSION_TYPE", parsed.reason_codes)

    def test_rejects_account_only_extension_on_mint(self):
        parsed = parse_token_2022_tlv(tlv(15, b"\x01"))
        self.assertEqual(parsed.validation_status, REJECTED)
        self.assertIn("ACCOUNT_EXTENSION_FOUND_IN_MINT", parsed.reason_codes)

    def test_empty_tlv_region_is_partial(self):
        for raw in (b"", bytes(8)):
            parsed = parse_token_2022_tlv(raw)
            self.assertEqual(parsed.validation_status, PARTIAL)
            self.assertIn("EMPTY_TLV_EXTENSION_REGION", parsed.reason_codes)

    def test_non_bytes_input_is_rejected(self):
        with self.assertRaises(DomainError):
            parse_token_2022_tlv("not-bytes")


class HeliusToken2022ExtensionReaderTests(unittest.TestCase):
    def reader(self, payload):
        calls = []

        def account_info(mint):
            calls.append(mint)
            return payload

        return HeliusToken2022ExtensionReader(
            account_info=account_info, clock=lambda: NOW
        ), calls

    def test_reads_finalized_token_2022_extension_evidence(self):
        reader, calls = self.reader(rpc_result())
        evidence = reader.read(SOL_MINT)
        self.assertEqual(calls, [SOL_MINT])
        self.assertEqual(evidence.validation_status, VERIFIED)
        self.assertEqual(evidence.extension_names, ("TRANSFER_HOOK",))
        self.assertIn("TRANSFER_HOOK_PRESENT", evidence.risk_flags)
        self.assertEqual(evidence.slot, 900)
        self.assertEqual(evidence.source_record_id, f"{SOL_MINT}:900:234")
        self.assertEqual(evidence.configuration.validation_status, VERIFIED)
        self.assertEqual(
            evidence.configuration.configurations[0].name, "TRANSFER_HOOK"
        )
        self.assertNotIn("SAFE", evidence.validation_status)

    def test_known_but_unsupported_extension_keeps_configuration_partial(self):
        reader, _ = self.reader(rpc_result(mint_data(tlv(4, bytes(295)))))
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, PARTIAL)
        self.assertEqual(evidence.configuration.validation_status, PARTIAL)
        self.assertEqual(evidence.configuration.unsupported_extension_ids, (4,))

    def test_unknown_extension_keeps_evidence_partial(self):
        reader, _ = self.reader(rpc_result(mint_data(tlv(65000, b"future"))))
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, PARTIAL)
        self.assertEqual(evidence.unknown_extension_ids, (65000,))

    def test_confirmed_classic_spl_mint_is_identified_without_token2022_extensions(self):
        reader, _ = self.reader(rpc_result(classic_mint_data(), owner=TOKEN_PROGRAM))
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, REJECTED)
        self.assertEqual(evidence.token_program, TOKEN_PROGRAM)
        self.assertEqual(evidence.reason_codes, ("CLASSIC_SPL_MINT_CONFIRMED",))
        self.assertEqual(evidence.account_data_length, 82)

    def test_classic_token_account_is_not_misclassified_as_a_mint(self):
        reader, _ = self.reader(rpc_result(owner=TOKEN_PROGRAM))
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, REJECTED)
        self.assertEqual(evidence.reason_codes, ("TOKEN_PROGRAM_ACCOUNT_NOT_MINT",))

    def test_uninitialized_classic_mint_is_rejected(self):
        reader, _ = self.reader(rpc_result(classic_mint_data(initialized=0), owner=TOKEN_PROGRAM))
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, REJECTED)
        self.assertEqual(evidence.reason_codes, ("MINT_NOT_INITIALIZED",))

    def test_missing_account_is_unavailable(self):
        reader, _ = self.reader({"context": {"slot": 901}, "value": None})
        evidence = reader.read(SOL_MINT)
        self.assertEqual(evidence.validation_status, UNAVAILABLE)
        self.assertEqual(evidence.reason_codes, ("MINT_ACCOUNT_NOT_FOUND",))

    def test_rejects_malformed_base64_and_space(self):
        payload = rpc_result()
        payload["value"]["data"] = ["%%%bad%%%", "base64"]
        reader, _ = self.reader(payload)
        with self.assertRaises(HeliusToken2022ExtensionMalformed):
            reader.read(SOL_MINT)

        payload = rpc_result()
        payload["value"]["space"] = 1
        reader, _ = self.reader(payload)
        with self.assertRaises(HeliusToken2022ExtensionMalformed):
            reader.read(SOL_MINT)

    def test_rejects_invalid_mint_layout_and_uninitialized_mint(self):
        # Too-short classic layout is malformed; mid-size buffer with zeroed
        # initialized flag is rejected (not treated as verified).
        reader, _ = self.reader(rpc_result(bytes(81)))
        with self.assertRaises(HeliusToken2022ExtensionMalformed):
            reader.read(SOL_MINT)

        for raw in (bytes(100), mint_data(initialized=0)):
            reader, _ = self.reader(rpc_result(raw))
            evidence = reader.read(SOL_MINT)
            self.assertEqual(evidence.validation_status, REJECTED)

        reader, _ = self.reader(rpc_result(mint_data(initialized=2)))
        with self.assertRaises(HeliusToken2022ExtensionMalformed):
            reader.read(SOL_MINT)

    def test_rejects_bad_slot_and_naive_clock(self):
        reader, _ = self.reader({"context": {"slot": True}, "value": None})
        with self.assertRaises(HeliusToken2022ExtensionMalformed):
            reader.read(SOL_MINT)

        reader = HeliusToken2022ExtensionReader(
            account_info=lambda _mint: rpc_result(),
            clock=lambda: datetime(2026, 11, 13),
        )
        with self.assertRaises(DomainError):
            reader.read(SOL_MINT)

    def test_rejects_invalid_mint_before_rpc(self):
        reader, calls = self.reader(rpc_result())
        with self.assertRaises(DomainError):
            reader.read("not-a-mint")
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main()
