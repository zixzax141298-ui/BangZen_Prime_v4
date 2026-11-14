"""Transactional outbox, processed-event store, and hash-chained audit log."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from bangzen_prime.domain.shared import DomainEvent
from bangzen_prime.infrastructure.persistence.sqlite.database import (
    Database,
    parse_iso,
    utc_iso,
)

GENESIS_HASH = "0" * 64


@dataclass(frozen=True)
class OutboxRow:
    id: str
    event_name: str
    payload: dict[str, Any]
    occurred_at: datetime
    attempts: int


class OutboxStore:
    """Writes events inside the caller's transaction; claims and settles them later."""

    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def enqueue(self, event: DomainEvent, at: datetime) -> None:
        self._conn.execute(
            "INSERT INTO outbox (id, event_name, payload, occurred_at, status, attempts,"
            " available_at) VALUES (?, ?, ?, ?, 'PENDING', 0, ?)",
            (
                event.event_id,
                event.name,
                json.dumps(event.payload, sort_keys=True),
                utc_iso(event.occurred_at),
                utc_iso(at),
            ),
        )

    def claim_due(self, now: datetime, lease: timedelta, limit: int) -> list[OutboxRow]:
        """Move due PENDING rows and expired PROCESSING leases to PROCESSING.

        Must be called inside Database.transaction() so the select and updates are atomic.
        """
        now_s = utc_iso(now)
        lease_s = utc_iso(now + lease)
        rows = self._conn.execute(
            "SELECT id FROM outbox WHERE (status = 'PENDING' AND available_at <= ?)"
            " OR (status = 'PROCESSING' AND lease_until <= ?)"
            " ORDER BY available_at LIMIT ?",
            (now_s, now_s, limit),
        ).fetchall()
        ids = [row["id"] for row in rows]
        for event_id in ids:
            self._conn.execute(
                "UPDATE outbox SET status = 'PROCESSING', lease_until = ? WHERE id = ?",
                (lease_s, event_id),
            )
        claimed = self._conn.execute(
            (
                # nosec B608 - Amand: Menggunakan parameter binding (?), bukan string interpolation
                f"SELECT * FROM outbox WHERE id IN ({','.join('?' * len(ids))})"  # nosec B608
                if ids
                else "SELECT * FROM outbox WHERE 0"
            ),
            tuple(ids),
        ).fetchall()
        return [
            OutboxRow(
                r["id"],
                r["event_name"],
                json.loads(r["payload"]),
                parse_iso(r["occurred_at"]),
                r["attempts"],
            )
            for r in claimed
        ]

    def mark_sent(self, event_id: str, at: datetime) -> None:
        self._conn.execute(
            "UPDATE outbox SET status = 'SENT', sent_at = ?, lease_until = NULL WHERE id = ?",
            (utc_iso(at), event_id),
        )

    def reschedule(
        self, event_id: str, *, attempts: int, available_at: datetime, error: str
    ) -> None:
        self._conn.execute(
            "UPDATE outbox SET status = 'PENDING', attempts = ?, available_at = ?,"
            " lease_until = NULL, last_error = ? WHERE id = ?",
            (attempts, utc_iso(available_at), error[:500], event_id),
        )

    def dead_letter(self, event_id: str, *, attempts: int, error: str) -> None:
        self._conn.execute(
            "UPDATE outbox SET status = 'FAILED', attempts = ?, lease_until = NULL,"
            " last_error = ? WHERE id = ?",
            (attempts, error[:500], event_id),
        )

    def status_of(self, event_id: str) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM outbox WHERE id = ?", (event_id,)
        ).fetchone()
        return dict(row) if row else None


class ProcessedEventStore:
    def __init__(self, db: Database) -> None:
        self._db = db

    def is_processed(self, subscriber: str, event_id: str) -> bool:
        return (
            self._db.query_one(
                "SELECT 1 FROM processed_events WHERE subscriber = ? AND event_id = ?",
                (subscriber, event_id),
            )
            is not None
        )

    def mark_processed(self, subscriber: str, event_id: str, at: datetime) -> None:
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO processed_events (subscriber, event_id, processed_at)"
                " VALUES (?, ?, ?)",
                (subscriber, event_id, utc_iso(at)),
            )


def _entry_hash(prev_hash: str, event_type: str, occurred_at: str, payload: str) -> str:
    material = f"{prev_hash}|{event_type}|{occurred_at}|{payload}".encode()
    return hashlib.sha256(material).hexdigest()


class AuditLog:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def append(self, event_type: str, payload: dict[str, Any], at: datetime) -> str:
        canonical = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), default=str
        )
        last = self._conn.execute(
            "SELECT hash FROM audit_log ORDER BY seq DESC LIMIT 1"
        ).fetchone()
        prev = last["hash"] if last else GENESIS_HASH
        when = utc_iso(at)
        digest = _entry_hash(prev, event_type, when, canonical)
        self._conn.execute(
            "INSERT INTO audit_log (event_type, payload, occurred_at, prev_hash, hash)"
            " VALUES (?, ?, ?, ?, ?)",
            (event_type, canonical, when, prev, digest),
        )
        return digest

    def verify(self) -> int | None:
        """Return the first broken sequence number, or None if the chain is intact."""
        prev = GENESIS_HASH
        for row in self._conn.execute("SELECT * FROM audit_log ORDER BY seq"):
            expected = _entry_hash(
                prev, row["event_type"], row["occurred_at"], row["payload"]
            )
            if row["prev_hash"] != prev or row["hash"] != expected:
                return int(row["seq"])
            prev = row["hash"]
        return None
