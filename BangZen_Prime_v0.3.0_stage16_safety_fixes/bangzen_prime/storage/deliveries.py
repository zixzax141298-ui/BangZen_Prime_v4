"""Delivery ledger for outbound notifications. Semantics: at-least-once, NOT exactly-once.

A key is claimed (SENDING, with a lease) before the channel is called and becomes SENT only
after the channel accepts the message. If the process crashes between the send and mark_sent,
the key stays SENDING. Once its lease expires it can be claimed again, so the same message may
be delivered twice. Receivers must tolerate duplicates. A key that is SENT is never resent.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime, timedelta

from bangzen_prime.core.errors import PersistenceError

MAX_ERROR_CHARS = 200


def stamp(value: datetime) -> str:
    """Fixed-width UTC timestamp, so string comparison in SQL matches time order."""
    if value.tzinfo is None:
        raise PersistenceError("naive datetime cannot be stored")
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f") + "Z"


class DeliveryStore:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self._conn = conn

    def claim(self, key: str, channel: str, now: datetime, lease: timedelta) -> bool:
        """True if this caller may send now. False if SENT, or SENDING with an unexpired lease."""
        ts = stamp(now)
        until = stamp(now + lease)
        self._conn.execute(
            "INSERT OR IGNORE INTO notification_deliveries "
            "(dedup_key, channel, status, attempts, updated_at) "
            "VALUES (?, ?, 'PENDING', 0, ?)",
            (key, channel, ts),
        )
        cursor = self._conn.execute(
            "UPDATE notification_deliveries SET status = 'SENDING', attempts = attempts + 1, "
            "lease_until = ?, updated_at = ? "
            "WHERE dedup_key = ? AND channel = ? AND ("
            "status IN ('PENDING', 'FAILED') "
            "OR (status = 'SENDING' AND lease_until < ?))",
            (until, ts, key, channel, ts),
        )
        return cursor.rowcount == 1

    def mark_sent(self, key: str, now: datetime) -> bool:
        ts = stamp(now)
        cursor = self._conn.execute(
            "UPDATE notification_deliveries SET status = 'SENT', sent_at = ?, updated_at = ?, "
            "lease_until = NULL, last_error = NULL WHERE dedup_key = ? AND status = 'SENDING'",
            (ts, ts, key),
        )
        return cursor.rowcount == 1

    def mark_failed(self, key: str, now: datetime, error: str) -> bool:
        ts = stamp(now)
        cursor = self._conn.execute(
            "UPDATE notification_deliveries SET status = 'FAILED', updated_at = ?, "
            "lease_until = NULL, last_error = ? WHERE dedup_key = ? AND status = 'SENDING'",
            (ts, error[:MAX_ERROR_CHARS], key),
        )
        return cursor.rowcount == 1

    def status(self, key: str) -> str | None:
        row = self._conn.execute(
            "SELECT status FROM notification_deliveries WHERE dedup_key = ?", (key,)
        ).fetchone()
        return None if row is None else row[0]
