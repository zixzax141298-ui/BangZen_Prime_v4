"""Order state machine for paper execution. Illegal transitions raise DomainError."""

from __future__ import annotations

from enum import StrEnum

from bangzen_prime.errors import DomainError


class OrderStatus(StrEnum):
    NEW = "NEW"
    FILLED = "FILLED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    REJECTED = "REJECTED"
    TIMEOUT = "TIMEOUT"
    CLOSED = "CLOSED"


_TRANSITIONS: dict[OrderStatus, frozenset[OrderStatus]] = {
    OrderStatus.NEW: frozenset(
        {
            OrderStatus.FILLED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.REJECTED,
            OrderStatus.TIMEOUT,
        }
    ),
    OrderStatus.FILLED: frozenset({OrderStatus.CLOSED}),
    OrderStatus.PARTIALLY_FILLED: frozenset({OrderStatus.CLOSED}),
    OrderStatus.REJECTED: frozenset(),
    OrderStatus.TIMEOUT: frozenset(),
    OrderStatus.CLOSED: frozenset(),
}
OPEN_STATUSES = frozenset({OrderStatus.FILLED, OrderStatus.PARTIALLY_FILLED})


def transition(current: OrderStatus, target: OrderStatus) -> OrderStatus:
    if target not in _TRANSITIONS[current]:
        raise DomainError(f"illegal order transition {current.value} -> {target.value}")
    return target
