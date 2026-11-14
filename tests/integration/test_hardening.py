import os
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime, timedelta

from bangzen_prime.domain.shared import DomainEvent
from bangzen_prime.domain.tokens import Token
from bangzen_prime.errors import PersistenceError
from bangzen_prime.infrastructure.observability.health import health_report
from bangzen_prime.infrastructure.persistence.sqlite import maintenance
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.infrastructure.persistence.sqlite.outbox import AuditLog, OutboxStore
from bangzen_prime.infrastructure.persistence.sqlite.repositories import UnitOfWork
from bangzen_prime.settings import Settings
from tests.support import START, TOKEN_MINT


def seeded_file_db(path, audit_entries=3):
    db = Database(path)
    db.migrate()
    with db.transaction() as conn:
        log = AuditLog(conn)
        for i in range(audit_entries):
            log.append("E", {"i": i}, START + timedelta(seconds=i))
        OutboxStore(conn).enqueue(
            DomainEvent("E", {}, START, event_id="old-sent"), START
        )
        conn.execute(
            "UPDATE outbox SET status='SENT', sent_at=? WHERE id='old-sent'",
            ("2025-01-01T00:00:00+00:00",),
        )
    return db


class DatabaseFailureTest(unittest.TestCase):
    def test_busy_database_becomes_persistence_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "busy.db")
            holder = Database(path)
            holder.migrate()
            blocker = sqlite3.connect(path, isolation_level=None)
            blocker.execute("BEGIN EXCLUSIVE")
            victim = Database(path)
            victim._conn.execute("PRAGMA busy_timeout = 1")  # fail fast in the test
            try:
                with self.assertRaises(PersistenceError):
                    with victim.transaction():
                        pass
            finally:
                blocker.execute("ROLLBACK")
                blocker.close()
                victim.close()
                holder.close()

    def test_interruption_mid_transaction_rolls_back(self):
        db = Database(":memory:")
        db.migrate()
        uow = UnitOfWork(db)
        with self.assertRaises(KeyboardInterrupt), uow.begin() as repos:
            repos.tokens.upsert(
                Token(chain="solana", mint=TOKEN_MINT, symbol="T"), START
            )
            raise KeyboardInterrupt()
        self.assertIsNone(db.query_one("SELECT 1 FROM tokens"))

    def test_integrity_errors_are_not_masked(self):
        db = Database(":memory:")
        db.migrate()
        with self.assertRaises(sqlite3.IntegrityError):
            with db.transaction() as conn:
                conn.execute(
                    "INSERT INTO pairs (id, token_id, chain, pair_address, dex_id, price_usd,"
                    " liquidity_usd, volume_24h_usd, observed_at) VALUES"
                    " ('p','missing','solana','a','d','1','1','1','x')"
                )


class BackupRestoreTest(unittest.TestCase):
    def test_backup_then_restore_roundtrip_keeps_audit_intact(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = seeded_file_db(os.path.join(tmp, "src.db"))
            bak = os.path.join(tmp, "bak.db")
            maintenance.backup(src, bak)
            target = os.path.join(tmp, "restored.db")
            maintenance.restore(bak, target)
            restored = Database(target)
            with restored.transaction() as conn:
                self.assertIsNone(AuditLog(conn).verify())
            self.assertEqual(
                restored.query_one("SELECT COUNT(*) AS n FROM audit_log")["n"], 3
            )
            restored.close()
            src.close()

    def test_tampered_backup_rejected_and_target_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = seeded_file_db(os.path.join(tmp, "src.db"))
            bak = os.path.join(tmp, "bak.db")
            maintenance.backup(src, bak)
            conn = sqlite3.connect(bak)
            conn.execute("UPDATE audit_log SET payload = '{\"i\":99}' WHERE seq = 2")
            conn.commit()
            conn.close()
            target = os.path.join(tmp, "live.db")
            with open(target, "wb") as fh:
                fh.write(b"original-live-data")
            with self.assertRaises(PersistenceError):
                maintenance.restore(bak, target)
            with open(target, "rb") as fh:
                self.assertEqual(fh.read(), b"original-live-data")
            src.close()

    def test_non_sqlite_file_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            junk = os.path.join(tmp, "junk.db")
            with open(junk, "wb") as fh:
                fh.write(b"this is not a database" * 100)
            with self.assertRaises(PersistenceError):
                maintenance.verify_database_file(junk)

    def test_missing_backup_rejected(self):
        with self.assertRaises(PersistenceError):
            maintenance.verify_database_file("/nonexistent/path/backup.db")

    def test_database_without_required_tables_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "empty.db")
            sqlite3.connect(path).close()
            with self.assertRaises(PersistenceError):
                maintenance.verify_database_file(path)


class RetentionTest(unittest.TestCase):
    def test_prune_removes_old_delivered_rows_but_never_audit(self):
        db = seeded_file_db(":memory:", audit_entries=4)
        result = maintenance.prune(
            db, now=START + timedelta(days=400), retain=timedelta(days=30)
        )
        self.assertEqual(result["outbox_sent_deleted"], 1)
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM audit_log")["n"], 4)
        with db.transaction() as conn:
            self.assertIsNone(AuditLog(conn).verify())

    def test_recent_rows_kept(self):
        db = seeded_file_db(":memory:")
        # seeded row is dated 2025-01-01; 15 Jan 2025 is inside the 30-day window
        result = maintenance.prune(
            db, now=datetime(2025, 1, 15, tzinfo=UTC), retain=timedelta(days=30)
        )
        self.assertEqual(result["outbox_sent_deleted"], 0)


class HealthTest(unittest.TestCase):
    def test_healthy_report(self):
        db = Database(":memory:")
        db.migrate()
        report = health_report(db, Settings())
        self.assertEqual(report["status"], "OK")
        self.assertEqual(report["database"], "OK")
        self.assertFalse(report["live_trading"])
        self.assertFalse(report["broadcast_enabled"])
        self.assertTrue(report["audit_intact"])

    def test_failed_outbox_marks_degraded(self):
        db = Database(":memory:")
        db.migrate()
        with db.transaction() as conn:
            OutboxStore(conn).enqueue(DomainEvent("E", {}, START, event_id="f"), START)
            OutboxStore(conn).dead_letter("f", attempts=5, error="x")
        self.assertEqual(health_report(db, Settings())["status"], "DEGRADED")

    def test_closed_database_reports_down(self):
        db = Database(":memory:")
        db.migrate()
        db.close()
        self.assertEqual(health_report(db, Settings())["status"], "DOWN")


if __name__ == "__main__":
    unittest.main()
