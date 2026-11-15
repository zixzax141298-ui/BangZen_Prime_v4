"""Exception hierarchy shared by every layer."""

from __future__ import annotations


class BangzenError(Exception):
    """Base class for all project errors."""


class ConfigurationError(BangzenError):
    """Settings are missing, invalid, or would enable an unsafe mode."""


class DomainError(BangzenError):
    """A domain invariant was violated."""


class ExternalServiceError(BangzenError):
    """An external service call failed. `retryable` tells the retry policy what to do."""

    def __init__(
        self,
        message: str,
        *,
        service: str,
        retryable: bool,
        status: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.service = service
        self.retryable = retryable
        self.status = status
        self.retry_after = retry_after


class CircuitOpenError(BangzenError):
    """The circuit breaker for a dependency is open; the call was not attempted."""


class PersistenceError(BangzenError):
    """Database access or migration failed."""


class EventDispatchError(BangzenError):
    """One or more subscribers failed while handling an event."""

    def __init__(self, failures: list[tuple[str, BaseException]]) -> None:
        self.failures = failures
        names = ", ".join(name for name, _ in failures)
        super().__init__(f"event dispatch failed for subscribers: {names}")
