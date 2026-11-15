"""Shared domain building blocks: entities, aggregates, and domain events."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from bangzen_prime.core.errors import DomainError


def utc_now() -> datetime:
    return datetime.now(UTC)


def ensure_utc(value: datetime) -> datetime:
    """Reject naive datetimes; normalise aware ones to UTC."""
    if (
        not isinstance(value, datetime)
        or value.tzinfo is None
        or value.utcoffset() is None
    ):
        raise DomainError("timestamp must be timezone-aware")
    return value.astimezone(UTC)


class Entity:
    """Identity-based entity: equal and hashable by (type, id)."""

    __slots__ = ("id",)

    def __init__(self, entity_id: uuid.UUID) -> None:
        if not isinstance(entity_id, uuid.UUID):
            raise DomainError("entity id must be a UUID")
        self.id = entity_id

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Entity):
            return NotImplemented
        return type(self) is type(other) and self.id == other.id

    def __hash__(self) -> int:
        return hash((type(self).__name__, self.id))


@dataclass
class DomainEvent:
    """Something that happened. `event_id` is stable across outbox retries."""

    name: str
    payload: dict[str, Any]
    occurred_at: datetime
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    def __post_init__(self) -> None:
        if not self.name:
            raise DomainError("event name must not be empty")
        self.occurred_at = ensure_utc(self.occurred_at)


class AggregateRoot(Entity):
    """Entity that buffers domain events until the application layer pulls them."""

    __slots__ = ("_events",)

    def __init__(self, entity_id: uuid.UUID) -> None:
        super().__init__(entity_id)
        self._events: list[DomainEvent] = []

    def record_event(
        self, name: str, payload: dict[str, Any], occurred_at: datetime
    ) -> DomainEvent:
        event = DomainEvent(name=name, payload=dict(payload), occurred_at=occurred_at)
        self._events.append(event)
        return event

    def pull_events(self) -> list[DomainEvent]:
        events, self._events = self._events, []
        return events
