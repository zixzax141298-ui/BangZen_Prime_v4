"""Backup, verified restore, and retention. Audit history is never pruned."""

from __future__ import annotations

import os
import pathlib
import sqlite3
from datetime import datetime, timedelta

from bangzen_prime.errors import PersistenceError
from bangzen_prime.infrastructure.persistence.sqlite.database import Database, utc_iso
from bangzen_prime.infrastructure.persistence.sqlite.outbox import AuditLog

REQUIRED_TABLES = frozenset({"tokens", "pairs", "signals", "outbox", "audit_log", "orders",
                             "ledger_entries", "chain_attempts", "schema_migrations"})


def backup(db: Database, dest_path: str) -> None:
    db.backup_to(dest_path)


def _open_readonly(path: str) -> sqlite3.Connection:
    """Open an existing file read-only. The path is converted to a URI with proper escaping.

    Building "file:{path}?mode=ro" by hand lets a path containing "?" add its own query
    parameters, for example "mode=rw", and so re-enable writes.
    """
    uri = pathlib.Path(path).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def verify_database_file(path: str) -> None:
    """Raise PersistenceError unless the file passes integrity, schema, and audit checks.

    Verification never writes to the file. The old code opened the backup with Database(),
    which runs PRAGMA journal_mode=WAL and rewrites the file header, so verifying a backup
    changed the backup.
    """
    if not os.path.exists(path):
        raise PersistenceError("backup file does not exist")
    try:
        conn = _open_readonly(path)
        try:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if integrity != "ok":
                raise PersistenceError("backup failed integrity check")
            missing = REQUIRED_TABLES - tables
            if missing:
                raise PersistenceError(f"backup is missing tables: {sorted(missing)}")
            broken = AuditLog(conn).verify()
        finally:
            conn.close()
    except sqlite3.DatabaseError as exc:
        raise PersistenceError("backup is not a valid SQLite database") from exc
    if broken is not None:
        raise PersistenceError(f"backup audit chain broken at seq {broken}")


def restore(backup_path: str, target_path: str) -> None:
    """Verify the backup, then atomically replace target. A failed verify leaves target untouched."""
    verify_database_file(backup_path)
    tmp = target_path + ".restore-tmp"
    with open(backup_path, "rb") as src, open(tmp, "wb") as dst:
        dst.write(src.read())
    verify_database_file(tmp)
    os.replace(tmp, target_path)


def prune(db: Database, *, now: datetime, retain: timedelta) -> dict[str, int]:
    """Delete delivered outbox rows and processed-event markers older than `retain`.

    Audit log, orders, ledger, and signals are never deleted here.
    """
    cutoff = utc_iso(now - retain)
    with db.transaction() as conn:
        sent = conn.execute("DELETE FROM outbox WHERE status = 'SENT' AND sent_at < ?",
                            (cutoff,)).rowcount
        processed = conn.execute("DELETE FROM processed_events WHERE processed_at < ?",
                                 (cutoff,)).rowcount
    return {"outbox_sent_deleted": sent, "processed_events_deleted": processed}
