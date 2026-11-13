"""Unit and persistence tests for validated Helius historical evidence."""

from __future__ import annotations

import json
import unittest
from datetime import UTC, datetime

from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.adapters.chain.helius_history import (
    HeliusHistoryMalformed,
    HeliusHistoryReader,
)
from bangzen_prime.infrastructure.http import HttpResponse
from bangzen_prime.infrastructure.persistence.sqlite.chain_history import ChainHistoryStore
from bangzen_prime.infrastructure.persistence.sqlite.database import Database

ADDRESS = "11111111111111111111111111111111"
SIG_A = "1" * 64
SIG_B = "1" * 63 + "2"
NOW = datetime(2026, 11, 13, 12, 0, tzinfo=UTC)


class FakeCaller:
    def call(self, fn):
        return fn()


class FakeTransport:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def __call__(self, request):
        self.requests.append(request)
        return HttpResponse(200, json.dumps(self.payload).encode(), {})


def reader(payload):
    transport = FakeTransport(payload)
    return HeliusHistoryReader(
        api_key="secret-key",
        transport=transport,
        caller=FakeCaller(),
        timeout=3,
        clock=lambda: NOW,
    ), transport


class HistoryReaderTests(unittest.TestCase):
    def test_signature_page_is_validated_and_newest_first(self):
        client, transport = reader({"jsonrpc": "2.0", "id": 1, "result": [
            {"signature": SIG_A, "slot": 10, "blockTime": 100, "err": None,
             "confirmationStatus": "finalized", "memo": None},
            {"signature": SIG_B, "slot": 9, "blockTime": None, "err": {"x": 1},
             "confirmationStatus": "confirmed", "memo": "memo"},
        ]})
        page = client.signatures_for_address(ADDRESS, limit=3)
        self.assertEqual([item.signature for item in page.entries], [SIG_A, SIG_B])
        self.assertTrue(page.exhausted)
        self.assertEqual(page.next_before_signature, SIG_B)
        self.assertTrue(page.entries[1].transaction_error)
        self.assertIn("api-key=secret-key", transport.requests[0].url)

    def test_full_page_is_not_mislabelled_exhausted(self):
        client, _ = reader({"jsonrpc": "2.0", "id": 1, "result": [
            {"signature": SIG_A, "slot": 10, "blockTime": 100, "err": None}
        ]})
        page = client.signatures_for_address(ADDRESS, limit=1)
        self.assertFalse(page.exhausted)

    def test_invalid_address_and_page_limit_rejected(self):
        client, _ = reader({"jsonrpc": "2.0", "id": 1, "result": []})
        with self.assertRaises(DomainError):
            client.signatures_for_address("bad")
        with self.assertRaises(DomainError):
            client.signatures_for_address(ADDRESS, limit=1001)
        with self.assertRaises(DomainError):
            client.signatures_for_address(ADDRESS, limit=True)

    def test_malformed_signature_or_slot_fails_closed(self):
        for item in (
            {"signature": "bad", "slot": 1, "err": None},
            {"signature": SIG_A, "slot": True, "err": None},
            {"signature": SIG_A, "slot": 1, "blockTime": -1, "err": None},
        ):
            client, _ = reader({"jsonrpc": "2.0", "id": 1, "result": [item]})
            with self.subTest(item=item), self.assertRaises(HeliusHistoryMalformed):
                client.signatures_for_address(ADDRESS)

    def test_duplicate_signatures_in_one_page_rejected(self):
        item = {"signature": SIG_A, "slot": 1, "err": None}
        client, _ = reader({"jsonrpc": "2.0", "id": 1, "result": [item, item]})
        with self.assertRaises(HeliusHistoryMalformed):
            client.signatures_for_address(ADDRESS)

    def test_page_with_ascending_slots_is_rejected(self):
        items = [
            {"signature": SIG_A, "slot": 9, "err": None},
            {"signature": SIG_B, "slot": 10, "err": None},
        ]
        client, _ = reader({"jsonrpc": "2.0", "id": 1, "result": items})
        with self.assertRaises(HeliusHistoryMalformed):
            client.signatures_for_address(ADDRESS)

    def test_transaction_parses_accounts_fees_and_balances(self):
        client, _ = reader({"jsonrpc": "2.0", "id": 1, "result": {
            "slot": 42, "blockTime": 123, "transaction": {"message": {
                "accountKeys": [{"pubkey": ADDRESS}, ADDRESS]
            }}, "meta": {
                "fee": 5000, "preBalances": [100, 200], "postBalances": [95, 205],
                "err": None
            }
        }})
        tx = client.transaction(SIG_A)
        self.assertTrue(tx.metadata_available)
        self.assertEqual(tx.fee_lamports, 5000)
        self.assertEqual(tx.account_keys, (ADDRESS, ADDRESS))
        self.assertEqual(tx.pre_balances, (100, 200))

    def test_transaction_without_meta_is_marked_unavailable(self):
        client, _ = reader({"jsonrpc": "2.0", "id": 1, "result": {
            "slot": 42, "blockTime": None, "transaction": {"message": {"accountKeys": []}},
            "meta": None
        }})
        tx = client.transaction(SIG_A)
        self.assertFalse(tx.metadata_available)

    def test_transaction_balance_length_mismatch_rejected(self):
        client, _ = reader({"jsonrpc": "2.0", "id": 1, "result": {
            "slot": 42, "transaction": {"message": {"accountKeys": [ADDRESS]}},
            "meta": {"fee": 1, "preBalances": [], "postBalances": [1], "err": None}
        }})
        with self.assertRaises(HeliusHistoryMalformed):
            client.transaction(SIG_A)


class ChainHistoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.migrate()
        self.store = ChainHistoryStore(self.db)

    def tearDown(self):
        self.db.close()

    def _page(self, entries, *, limit=2):
        from bangzen_prime.infrastructure.adapters.chain.helius_history import (
            HistoricalSignaturePage,
        )
        return HistoricalSignaturePage(
            address=ADDRESS,
            entries=tuple(entries),
            requested_limit=limit,
            before_signature=None,
            until_signature=None,
            next_before_signature=entries[-1].signature if entries else None,
            exhausted=len(entries) < limit,
            observed_at=NOW,
        )

    def test_page_insert_and_checkpoint_are_atomic_and_idempotent(self):
        from bangzen_prime.infrastructure.adapters.chain.helius_history import HistoricalSignature
        entry = HistoricalSignature(SIG_A, 10, 100, False, "finalized", None)
        self.assertEqual(self.store.record_page(self._page([entry])), 1)
        self.assertEqual(self.store.record_page(self._page([entry])), 0)
        self.assertEqual(self.store.signature_count(ADDRESS), 1)
        checkpoint = self.store.checkpoint(ADDRESS)
        self.assertEqual(checkpoint.before_signature, SIG_A)
        self.assertEqual(checkpoint.coverage_status, "EXHAUSTED")
        self.assertEqual(checkpoint.pages_fetched, 2)

    def test_more_available_checkpoint_retains_cursor(self):
        from bangzen_prime.infrastructure.adapters.chain.helius_history import HistoricalSignature
        entries = [
            HistoricalSignature(SIG_A, 10, 100, False, None, None),
            HistoricalSignature(SIG_B, 9, 99, False, None, None),
        ]
        self.store.record_page(self._page(entries, limit=2))
        checkpoint = self.store.checkpoint(ADDRESS)
        self.assertEqual(checkpoint.coverage_status, "MORE_AVAILABLE")
        self.assertEqual(checkpoint.before_signature, SIG_B)

    def test_failed_checkpoint_never_claims_exhaustion(self):
        self.store.mark_failed(ADDRESS, NOW)
        self.assertEqual(self.store.checkpoint(ADDRESS).coverage_status, "FAILED")


if __name__ == "__main__":
    unittest.main()
