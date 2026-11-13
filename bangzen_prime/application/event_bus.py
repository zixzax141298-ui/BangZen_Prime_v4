"""In-process event bus. Runs every subscriber, then raises an aggregate error if any failed.

Failures are never swallowed: the outbox worker sees EventDispatchError and retries.
Per-subscriber deduplication uses processed_events, so a retry does not re-run subscribers
that already succeeded.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from bangzen_prime.domain.shared import DomainEvent
from bangzen_prime.errors import EventDispatchError

logger = logging.getLogger("bangzen_prime.events")
Handler = Callable[[DomainEvent], None]


@dataclass(frozen=True)
class Subscription:
    name: str
    handler: Handler


class ProcessedStore:
    """Protocol-like contract: is_processed / mark_processed per subscriber and event id."""

    def is_processed(self, subscriber: str, event_id: str) -> bool: ...  # pragma: no cover

    def mark_processed(self, subscriber: str, event_id: str, at: datetime) -> None: ...  # pragma: no cover


class EventBus:
    def __init__(self, processed: ProcessedStore, clock: Callable[[], datetime]) -> None:
        self._processed = processed
        self._clock = clock
        self._subs: dict[str, list[Subscription]] = {}

    def subscribe(self, event_name: str, subscriber: str, handler: Handler) -> None:
        existing = self._subs.setdefault(event_name, [])
        if any(s.name == subscriber for s in existing):
            raise ValueError(f"duplicate subscriber {subscriber!r} for {event_name}")
        existing.append(Subscription(subscriber, handler))

    def dispatch(self, event: DomainEvent) -> None:
        failures: list[tuple[str, BaseException]] = []
        for sub in self._subs.get(event.name, []):
            if self._processed.is_processed(sub.name, event.event_id):
                continue
            try:
                sub.handler(event)
            except Exception as exc:  # noqa: BLE001 - collected and re-raised below
                logger.error("subscriber %s failed for %s: %s", sub.name, event.name,
                             type(exc).__name__)
                failures.append((sub.name, exc))
                continue
            self._processed.mark_processed(sub.name, event.event_id, self._clock())
        if failures:
            raise EventDispatchError(failures)
