import sqlite3
import unittest
import uuid
from datetime import datetime, timedelta
from decimal import Decimal

from bangzen_prime.domain.shared import DomainEvent
from bangzen_prime.domain.signals import PriceLevels, RejectReason, Signal, SignalStatus
from bangzen_prime.domain.tokens import PairSnapshot, SafetyAssessment, Token
from bangzen_prime.errors import PersistenceError
from bangzen_prime.infrastructure.persistence.sqlite.database import Database, load_migrations
from bangzen_prime.infrastructure.persistence.sqlite.outbox import (
    GENESIS_HASH,
    AuditLog,
    OutboxStore,
    ProcessedEventStore,
)
from bangzen_prime.infrastructure.persistence.sqlite.repositories import UnitOfWork
from tests.support import PAIR_ADDRESS, START, TOKEN_MINT


def fresh_db():
    db = Database(":memory:")
    db.migrate()
    return db


def seed_token(uow):
    token = Token(chain="solana", mint=TOKEN_MINT, symbol="TEST")
    pair = PairSnapshot.create(chain="solana", pair_address=PAIR_ADDRESS, dex_id="raydium",
                               base_mint=TOKEN_MINT, base_symbol="TEST", price_usd="1.25",
                               liquidity_usd="50000", volume_24h_usd="20000", observed_at=START)
    with uow.begin() as repos:
        repos.tokens.upsert(token, START)
        repos.pairs.upsert(pair)
    return token, pair


class MigrationTest(unittest.TestCase):
    def test_fresh_database_applies_all_migrations_once(self):
        db = Database(":memory:")
        self.assertEqual(db.migrate(), [1, 2, 3, 4, 5])
        self.assertEqual(db.migrate(), [])  # idempotent
        names = {r["name"] for r in db.query_all("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"tokens", "pairs", "signals", "outbox", "audit_log", "orders",
                         "ledger_entries", "token_lifecycle", "token_lifecycle_events"} <= names)

    def test_migrations_are_loaded_from_package_data(self):
        migrations = load_migrations()
        self.assertEqual([v for v, _, _ in migrations], [1, 2, 3, 4, 5])
        self.assertTrue(all("CREATE TABLE" in sql for _, _, sql in migrations))

    def test_schema_version_recorded(self):
        db = fresh_db()
        self.assertEqual([r["version"] for r in db.query_all(
            "SELECT version FROM schema_migrations ORDER BY version")], [1, 2, 3, 4, 5])


class TransactionTest(unittest.TestCase):
    def test_rollback_removes_all_writes_of_failed_unit_of_work(self):
        db = fresh_db()
        uow = UnitOfWork(db)
        with self.assertRaises(RuntimeError):
            with uow.begin() as repos:
                token = Token(chain="solana", mint=TOKEN_MINT, symbol="T")
                repos.tokens.upsert(token, START)
                raise RuntimeError("boom mid-transaction")
        self.assertIsNone(db.query_one("SELECT 1 FROM tokens"))

    def test_token_signal_and_outbox_commit_together(self):
        db = fresh_db()
        uow = UnitOfWork(db)
        token, pair = seed_token(uow)
        signal = Signal.accept(token_id=token.id, pair_id=pair.pair_id, score=Decimal(60),
                               confidence=Decimal("0.6"),
                               levels=PriceLevels(Decimal("1.25"), Decimal("1.1"), Decimal("1.6")),
                               created_at=START)
        with uow.begin() as repos:
            repos.signals.add(signal)
            for event in signal.pull_events():
                repos.outbox.enqueue(event, START)
                repos.audit.append(event.name, event.payload, START)
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM outbox")["n"], 1)
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM audit_log")["n"], 1)

    def test_foreign_key_violation_rolls_back(self):
        db = fresh_db()
        uow = UnitOfWork(db)
        signal = Signal.reject(token_id=uuid.uuid4(), pair_id=uuid.uuid4(), score=Decimal(0),
                               reasons=(RejectReason.EMPTY_MARKET,), created_at=START)
        with self.assertRaises(sqlite3.IntegrityError):
            with uow.begin() as repos:
                repos.signals.add(signal)
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM signals")["n"], 0)

    def test_check_constraint_blocks_accepted_without_levels(self):
        db = fresh_db()
        with self.assertRaises(sqlite3.IntegrityError):
            with db.transaction() as conn:
                conn.execute("INSERT INTO signals (id, token_id, pair_id, status, score, reasons,"
                             " created_at) VALUES ('x', 'a', 'b', 'ACCEPTED', '1', '[]', 'c')")


class RoundTripTest(unittest.TestCase):
    def test_signal_roundtrip_returns_datetime_and_decimal(self):
        db = fresh_db()
        uow = UnitOfWork(db)
        token, pair = seed_token(uow)
        levels = PriceLevels(Decimal("1.25"), Decimal("1.1"), Decimal("1.6"))
        signal = Signal.accept(token_id=token.id, pair_id=pair.pair_id, score=Decimal("61.5"),
                               confidence=Decimal("0.615"), levels=levels, created_at=START)
        with uow.begin() as repos:
            repos.signals.add(signal)
        with uow.begin() as repos:
            loaded = repos.signals.get(signal.id)
        self.assertIsInstance(loaded.created_at, datetime)
        self.assertEqual(loaded.created_at, START)
        self.assertEqual(loaded.levels, levels)
        self.assertEqual(loaded.confidence, Decimal("0.615"))
        self.assertEqual(loaded.status, SignalStatus.ACCEPTED)

    def test_rejected_signal_reasons_are_structured(self):
        db = fresh_db()
        uow = UnitOfWork(db)
        token, pair = seed_token(uow)
        signal = Signal.reject(token_id=token.id, pair_id=pair.pair_id, score=Decimal(0),
                               reasons=(RejectReason.RUGGED, RejectReason.LOW_LIQUIDITY),
                               created_at=START)
        with uow.begin() as repos:
            repos.signals.add(signal)
        with uow.begin() as repos:
            loaded = repos.signals.get(signal.id)
        self.assertEqual(loaded.reasons, (RejectReason.RUGGED, RejectReason.LOW_LIQUIDITY))
        self.assertIsNone(loaded.levels)

    def test_price_history_is_chronological_and_limited(self):
        db = fresh_db()
        uow = UnitOfWork(db)
        token, _ = seed_token(uow)
        with uow.begin() as repos:
            for i in range(1, 6):
                repos.prices.append(token.id, Decimal(i) / Decimal(10), START)
        with uow.begin() as repos:
            recent = repos.prices.recent(token.id, 3)
        self.assertEqual(recent, [Decimal("0.3"), Decimal("0.4"), Decimal("0.5")])

    def test_safety_and_pair_upsert_idempotent(self):
        db = fresh_db()
        uow = UnitOfWork(db)
        token, pair = seed_token(uow)
        assessment = SafetyAssessment.create(chain="solana", mint=TOKEN_MINT, risk_score="12",
                                             rugged=False, source="rugcheck", checked_at=START)
        with uow.begin() as repos:
            repos.safety.append(token.id, assessment)
            repos.pairs.upsert(pair)
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM pairs")["n"], 1)
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM safety_checks")["n"], 1)


class AuditChainTest(unittest.TestCase):
    def build(self, n=3):
        db = fresh_db()
        with db.transaction() as conn:
            log = AuditLog(conn)
            for i in range(n):
                log.append("E", {"i": i}, START + timedelta(seconds=i))
        return db

    def test_chain_is_intact_after_appends(self):
        db = self.build()
        with db.transaction() as conn:
            self.assertIsNone(AuditLog(conn).verify())
        first = db.query_one("SELECT prev_hash FROM audit_log ORDER BY seq LIMIT 1")
        self.assertEqual(first["prev_hash"], GENESIS_HASH)

    def test_tampered_payload_is_detected(self):
        db = self.build()
        with db.transaction() as conn:
            conn.execute("UPDATE audit_log SET payload = '{\"i\":99}' WHERE seq = 2")
        with db.transaction() as conn:
            self.assertEqual(AuditLog(conn).verify(), 2)

    def test_deleted_row_breaks_chain(self):
        db = self.build()
        with db.transaction() as conn:
            conn.execute("DELETE FROM audit_log WHERE seq = 2")
        with db.transaction() as conn:
            self.assertEqual(AuditLog(conn).verify(), 3)


def make_event(event_id=None, at=START):
    return DomainEvent(name="SignalGenerated", payload={"n": 1}, occurred_at=at,
                       event_id=event_id or str(uuid.uuid4()))


class OutboxTest(unittest.TestCase):
    def enqueue(self, db, event):
        with db.transaction() as conn:
            OutboxStore(conn).enqueue(event, START)

    def claim(self, db, now, lease=timedelta(seconds=30), limit=10):
        with db.transaction() as conn:
            return OutboxStore(conn).claim_due(now, lease, limit)

    def test_due_event_is_claimed_once(self):
        db = fresh_db()
        self.enqueue(db, make_event("e1"))
        first = self.claim(db, START)
        second = self.claim(db, START)
        self.assertEqual([r.id for r in first], ["e1"])
        self.assertEqual(second, [])  # lease held: not claimable by a second worker

    def test_future_available_at_not_claimed(self):
        db = fresh_db()
        with db.transaction() as conn:
            OutboxStore(conn).enqueue(make_event("later"), START + timedelta(hours=1))
        self.assertEqual(self.claim(db, START), [])

    def test_expired_lease_is_recovered(self):
        db = fresh_db()
        self.enqueue(db, make_event("crash"))
        self.claim(db, START, lease=timedelta(seconds=30))
        self.assertEqual(self.claim(db, START + timedelta(seconds=29)), [])
        recovered = self.claim(db, START + timedelta(seconds=31))
        self.assertEqual([r.id for r in recovered], ["crash"])

    def test_reschedule_and_dead_letter(self):
        db = fresh_db()
        self.enqueue(db, make_event("r1"))
        self.claim(db, START)
        with db.transaction() as conn:
            OutboxStore(conn).reschedule("r1", attempts=1, available_at=START + timedelta(minutes=1),
                                         error="fail")
        self.assertEqual(self.claim(db, START), [])
        self.assertEqual([r.id for r in self.claim(db, START + timedelta(minutes=1))], ["r1"])
        with db.transaction() as conn:
            OutboxStore(conn).dead_letter("r1", attempts=5, error="gave up")
        row = db.query_one("SELECT status, attempts, last_error FROM outbox WHERE id = 'r1'")
        self.assertEqual((row["status"], row["attempts"], row["last_error"]), ("FAILED", 5, "gave up"))

    def test_mark_sent_and_status_query(self):
        db = fresh_db()
        self.enqueue(db, make_event("s1"))
        self.claim(db, START)
        with db.transaction() as conn:
            OutboxStore(conn).mark_sent("s1", START)
            self.assertEqual(OutboxStore(conn).status_of("s1")["status"], "SENT")
        self.assertEqual(self.claim(db, START + timedelta(days=1)), [])

    def test_processed_events_store(self):
        db = fresh_db()
        store = ProcessedEventStore(db)
        self.assertFalse(store.is_processed("sub", "e"))
        store.mark_processed("sub", "e", START)
        store.mark_processed("sub", "e", START)  # idempotent insert
        self.assertTrue(store.is_processed("sub", "e"))
        self.assertFalse(store.is_processed("other", "e"))

    def test_invalid_status_value_rejected_by_schema(self):
        db = fresh_db()
        with self.assertRaises(sqlite3.IntegrityError):
            with db.transaction() as conn:
                conn.execute("INSERT INTO outbox (id, event_name, payload, occurred_at, status,"
                             " available_at) VALUES ('z', 'E', '{}', 'x', 'BOGUS', 'x')")


class DatabaseErrorTest(unittest.TestCase):
    def test_persistence_error_type_exists_for_callers(self):
        self.assertTrue(issubclass(PersistenceError, Exception))


if __name__ == "__main__":
    unittest.main()
