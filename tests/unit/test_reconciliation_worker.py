import unittest
from decimal import Decimal

from bangzen_prime.application.heartbeat import EmergencyLatch
from bangzen_prime.application.reconciliation import (
    STATUS_MISMATCH,
    STATUS_NOT_CONFIGURED,
    STATUS_OK,
    STATUS_UNAVAILABLE,
    ReconciliationWorker,
)
from bangzen_prime.errors import ExternalServiceError
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from tests.support import START, TOKEN_MINT

OWNER = "HxFLKUAmAMLz1jtT3hbvCMELwH5H9tpM2QugP8sKyfhc"
TS = START.isoformat()


class FixedBalance:
    def __init__(self, value):
        self.value = value
        self.calls = []

    def token_balance(self, owner, mint):
        self.calls.append((owner, mint))
        if isinstance(self.value, Exception):
            raise self.value
        return self.value


def seed_order(db, idx, status, filled, *, mint=TOKEN_MINT):
    """Insert the minimal token/pair/signal/order chain that a real order would have."""
    with db.transaction() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO tokens (id, chain, mint, symbol, name, created_at)"
            " VALUES (?, 'solana', ?, 'X', '', ?)", (f"tok-{mint}", mint, TS))
        conn.execute(
            "INSERT OR IGNORE INTO pairs (id, token_id, chain, pair_address, dex_id, price_usd,"
            " liquidity_usd, volume_24h_usd, observed_at)"
            " VALUES (?, ?, 'solana', ?, 'dex', '1', '1', '1', ?)",
            (f"pair-{mint}", f"tok-{mint}", f"pool-{mint}", TS))
        conn.execute(
            "INSERT INTO signals (id, token_id, pair_id, status, score, entry_price, stop_loss,"
            " take_profit, confidence, reasons, created_at)"
            " VALUES (?, ?, ?, 'ACCEPTED', '1', '1', '0.9', '1.1', '0.5', '[]', ?)",
            (f"sig-{idx}", f"tok-{mint}", f"pair-{mint}", TS))
        conn.execute(
            "INSERT INTO orders (id, idempotency_key, signal_id, token_id, status, requested_units,"
            " filled_units, entry_price, stop_loss, take_profit, created_at)"
            " VALUES (?, ?, ?, ?, ?, '100', ?, '1', '0.9', '1.1', ?)",
            (f"ord-{idx}", f"key-{idx}", f"sig-{idx}", f"tok-{mint}", status, str(filled), TS))


class ReconciliationAccountingTests(unittest.TestCase):
    def setUp(self):
        self.db = Database(":memory:")
        self.db.migrate()
        self.latch = EmergencyLatch()

    def worker(self, balance, tolerance="1"):
        return ReconciliationWorker(db=self.db, balances=balance, owner=OWNER,
                                    tolerance_pct=Decimal(tolerance), latch=self.latch)

    def test_expected_counts_only_open_filled_units(self):
        seed_order(self.db, 1, "FILLED", "40")
        seed_order(self.db, 2, "PARTIALLY_FILLED", "10")
        seed_order(self.db, 3, "CLOSED", "999")
        seed_order(self.db, 4, "NEW", "777")
        seed_order(self.db, 5, "REJECTED", "555")
        self.assertEqual(self.worker(None).expected_units(TOKEN_MINT), Decimal("50"))

    def test_other_mints_are_not_counted(self):
        seed_order(self.db, 1, "FILLED", "40", mint="OtherMint111111111111111111111111111111111")
        self.assertEqual(self.worker(None).expected_units(TOKEN_MINT), Decimal("0"))

    def test_observed_equal_to_open_units_is_ok(self):
        seed_order(self.db, 1, "FILLED", "40")
        r = self.worker(FixedBalance(Decimal("40"))).run_once(TOKEN_MINT, START)
        self.assertEqual(r.status, STATUS_OK)
        self.assertFalse(self.latch.is_active)

    def test_tolerance_boundary_is_inclusive_and_exceeded_is_mismatch(self):
        seed_order(self.db, 1, "FILLED", "100")
        ok = self.worker(FixedBalance(Decimal("101")), tolerance="1").run_once(TOKEN_MINT, START)
        self.assertEqual(ok.status, STATUS_OK)
        bad = self.worker(FixedBalance(Decimal("101.01")), tolerance="1").run_once(TOKEN_MINT, START)
        self.assertEqual(bad.status, STATUS_MISMATCH)
        self.assertTrue(self.latch.is_active)

    def test_mismatch_writes_audit_event_and_trips_latch_once(self):
        seed_order(self.db, 1, "FILLED", "40")
        self.worker(FixedBalance(Decimal("0"))).run_once(TOKEN_MINT, START)
        self.worker(FixedBalance(Decimal("0"))).run_once(TOKEN_MINT, START)
        events = [row["event_type"] for row in self.db.query_all("SELECT event_type FROM audit_log")]
        self.assertEqual(events.count("ReconciliationMismatch"), 2)
        self.assertTrue(self.latch.reason.startswith("RECONCILIATION_MISMATCH"))

    def test_string_balance_from_provider_is_normalised(self):
        seed_order(self.db, 1, "FILLED", "40")
        r = self.worker(FixedBalance("40")).run_once(TOKEN_MINT, START)
        self.assertEqual(r.status, STATUS_OK)
        self.assertEqual(r.observed_units, Decimal("40"))

    def test_invalid_balances_fail_closed_without_tripping_latch(self):
        for bad in (Decimal("-1"), "not-a-number", Decimal("NaN"), Decimal("Infinity")):
            with self.subTest(bad=bad):
                r = self.worker(FixedBalance(bad)).run_once(TOKEN_MINT, START)
                self.assertEqual(r.status, STATUS_UNAVAILABLE)
                self.assertFalse(self.latch.is_active)

    def test_provider_outage_is_unavailable_and_never_ok(self):
        seed_order(self.db, 1, "FILLED", "40")
        r = self.worker(FixedBalance(ExternalServiceError("rpc down", service="helius", retryable=True))
                        ).run_once(TOKEN_MINT, START)
        self.assertEqual(r.status, STATUS_UNAVAILABLE)
        self.assertFalse(self.latch.is_active)

    def test_no_balance_provider_is_not_configured_and_skips_provider(self):
        seed_order(self.db, 1, "FILLED", "40")
        r = self.worker(None).run_once(TOKEN_MINT, START)
        self.assertEqual(r.status, STATUS_NOT_CONFIGURED)
        self.assertFalse(self.latch.is_active)

    def test_provider_queried_with_configured_owner(self):
        balance = FixedBalance(Decimal("0"))
        self.worker(balance).run_once(TOKEN_MINT, START)
        self.assertEqual(balance.calls, [(OWNER, TOKEN_MINT)])

    def test_constructor_rejects_bad_inputs(self):
        for kwargs in (
            {"owner": "  ", "tolerance_pct": Decimal("1")},
            {"owner": OWNER, "tolerance_pct": Decimal("101")},
            {"owner": OWNER, "tolerance_pct": Decimal("-0.1")},
            {"owner": OWNER, "tolerance_pct": Decimal("NaN")},
            {"owner": OWNER, "tolerance_pct": 1.0},
        ):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                ReconciliationWorker(db=self.db, balances=None, latch=self.latch, **kwargs)


if __name__ == "__main__":
    unittest.main()
