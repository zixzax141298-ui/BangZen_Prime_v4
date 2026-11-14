"""SQLite connection with serialised, explicit transactions and packaged migrations.

Concurrency model: one connection per Database object, guarded by an RLock so that
threads in one process never interleave transactions on the same connection. Multiple
processes are safe through SQLite's own file locking (BEGIN IMMEDIATE takes the write lock
up front, so claims and updates cannot interleave).
"""

from __future__ import annotations

import os
import re
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from importlib import resources

from bangzen_prime.errors import PersistenceError

_MIGRATION_NAME = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")
_MIGRATION_PACKAGE = "bangzen_prime.infrastructure.migrations"


def load_migrations() -> list[tuple[int, str, str]]:
    """Return (version, name, sql) sorted by version, read from installed package data."""
    found: list[tuple[int, str, str]] = []
    for entry in resources.files(_MIGRATION_PACKAGE).iterdir():
        match = _MIGRATION_NAME.match(entry.name)
        if match:
            found.append(
                (int(match.group(1)), match.group(2), entry.read_text("utf-8"))
            )
    found.sort(key=lambda item: item[0])
    versions = [v for v, _, _ in found]
    if versions != list(range(1, len(versions) + 1)):
        raise PersistenceError("migration versions must be contiguous from 0001")
    return found


def split_statements(sql: str) -> list[str]:
    lines = [line for line in sql.splitlines() if not line.lstrip().startswith("--")]
    statements = [part.strip() for part in "\n".join(lines).split(";")]
    return [s for s in statements if s]


def utc_iso(value: datetime) -> str:
    if value.tzinfo is None:
        raise PersistenceError("naive datetime cannot be stored")
    return value.astimezone(UTC).isoformat()


def parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


class Database:
    def __init__(self, path: str = ":memory:") -> None:
        self.path = path
        self._conn = sqlite3.connect(
            path, isolation_level=None, check_same_thread=False
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._conn.execute("PRAGMA busy_timeout = 5000")
        if path != ":memory:":
            self._conn.execute("PRAGMA journal_mode = WAL")
        self._lock = threading.RLock()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """One serialised transaction. Any exception rolls back. Busy or unavailable DB -> PersistenceError."""
        with self._lock:
            try:
                self._conn.execute("BEGIN IMMEDIATE")
            except sqlite3.OperationalError as exc:
                raise PersistenceError("database busy or unavailable") from exc
            try:
                yield self._conn
            except BaseException as exc:
                try:
                    self._conn.execute("ROLLBACK")
                except sqlite3.Error:
                    pass
                if isinstance(exc, sqlite3.OperationalError):
                    raise PersistenceError("database operation failed") from exc
                raise
            try:
                self._conn.execute("COMMIT")
            except sqlite3.OperationalError as exc:
                raise PersistenceError("commit failed") from exc

    def backup_to(self, dest_path: str) -> None:
        """Consistent online copy using SQLite's backup API, written atomically to dest_path."""
        tmp = dest_path + ".tmp"
        with self._lock:
            target = sqlite3.connect(tmp)
            try:
                self._conn.backup(target)
            finally:
                target.close()
        os.replace(tmp, dest_path)

    def query_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self._conn.execute(sql, params).fetchone()

    def query_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self._conn.execute(sql, params).fetchall()

    def migrate(self) -> list[int]:
        """Apply pending migrations. Idempotent: re-running applies nothing new."""
        applied_now: list[int] = []
        with self._lock:
            self._conn.execute(
                "CREATE TABLE IF NOT EXISTS schema_migrations ("
                "version INTEGER PRIMARY KEY, name TEXT NOT NULL, applied_at TEXT NOT NULL)"
            )
        done = {
            row["version"]
            for row in self.query_all("SELECT version FROM schema_migrations")
        }
        for version, name, sql in load_migrations():
            if version in done:
                continue
            with self.transaction() as conn:
                for statement in split_statements(sql):
                    conn.execute(statement)
                conn.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (version, name, utc_iso(datetime.now(UTC))),
                )
            applied_now.append(version)
        return applied_now
