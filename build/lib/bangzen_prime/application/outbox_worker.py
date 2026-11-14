"""Outbox worker: claims due events, dispatches them, and settles each row.

Delivery is at-least-once. A crash after a subscriber acts but before processed_events is
written, or after dispatch but before mark_sent, causes a redelivery. Subscribers must
therefore be idempotent or tolerate duplicates. Exactly-once is NOT claimed.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from bangzen_prime.application.event_bus import EventBus
from bangzen_prime.domain.shared import DomainEvent
from bangzen_prime.errors import EventDispatchError
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.infrastructure.persistence.sqlite.outbox import OutboxStore

logger = logging.getLogger("bangzen_prime.outbox")


@dataclass
class WorkerStats:
    claimed: int = 0
    sent: int = 0
    retried: int = 0
    dead_lettered: int = 0


class OutboxWorker:
    def __init__(
        self,
        *,
        db: Database,
        bus: EventBus,
        clock: Callable[[], datetime],
        max_attempts: int = 5,
        base_backoff: timedelta = timedelta(seconds=5),
        lease: timedelta = timedelta(seconds=30),
    ) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._db = db
        self._bus = bus
        self._clock = clock
        self._max_attempts = max_attempts
        self._base_backoff = base_backoff
        self._lease = lease

    def run_once(self, limit: int = 20) -> WorkerStats:
        stats = WorkerStats()
        now = self._clock()
        with self._db.transaction() as conn:
            rows = OutboxStore(conn).claim_due(now, self._lease, limit)
        stats.claimed = len(rows)
        for row in rows:
            event = DomainEvent(
                name=row.event_name,
                payload=row.payload,
                occurred_at=row.occurred_at,
                event_id=row.id,
            )
            try:
                self._bus.dispatch(event)
            except EventDispatchError as exc:
                attempts = row.attempts + 1
                now = self._clock()
                with self._db.transaction() as conn:
                    store = OutboxStore(conn)
                    if attempts >= self._max_attempts:
                        store.dead_letter(row.id, attempts=attempts, error=str(exc))
                        stats.dead_lettered += 1
                        logger.error("outbox event %s dead-lettered", row.id)
                    else:
                        delay = self._base_backoff * (2 ** (attempts - 1))
                        store.reschedule(
                            row.id,
                            attempts=attempts,
                            available_at=now + delay,
                            error=str(exc),
                        )
                        stats.retried += 1
                continue
            with self._db.transaction() as conn:
                OutboxStore(conn).mark_sent(row.id, self._clock())
            stats.sent += 1
        return stats
