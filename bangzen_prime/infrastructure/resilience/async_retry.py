"""Async retry helper for transient network / external-service failures.

Complements the sync ResilientCaller used by HTTP adapters. Application-layer
async orchestration (e.g. ExecutionUseCase) uses this helper so retries stay
testable without real sleeps and respect ExternalServiceError.retryable.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import TypeVar

from bangzen_prime.errors import CircuitOpenError, ExternalServiceError
from bangzen_prime.infrastructure.resilience.policies import RetryPolicy

logger = logging.getLogger("bangzen_prime.async_retry")

T = TypeVar("T")

# Network-ish exception types treated as retryable when not ExternalServiceError
_DEFAULT_RETRYABLE_TYPES: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    asyncio.TimeoutError,
    OSError,
)


@dataclass(frozen=True)
class RetryOutcome:
    """Optional diagnostics for callers that want attempt metrics."""

    attempts: int
    succeeded: bool
    last_error: BaseException | None = None


def is_retryable_error(
    exc: BaseException,
    *,
    extra_retryable: tuple[type[BaseException], ...] = (),
) -> bool:
    """Return True only for transient failures; never for policy/business rejects."""
    if isinstance(exc, CircuitOpenError):
        return False
    if isinstance(exc, ExternalServiceError):
        return bool(exc.retryable)
    types = _DEFAULT_RETRYABLE_TYPES + extra_retryable
    return isinstance(exc, types)


async def async_retry(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    operation_name: str = "operation",
    extra_retryable: tuple[type[BaseException], ...] = (),
    on_retry: Callable[[int, BaseException, float], None] | None = None,
) -> T:
    """Run ``operation`` with exponential backoff on retryable errors.

    Non-retryable errors and exhausted attempts are re-raised unchanged.
    ``sleep`` defaults to ``asyncio.sleep``; inject a no-op async sleep in tests.
    """
    retry = policy or RetryPolicy()
    sleep_fn = sleep or asyncio.sleep
    attempt = 0
    last_exc: BaseException | None = None

    while True:
        attempt += 1
        try:
            return await operation()
        except BaseException as exc:
            last_exc = exc
            if not is_retryable_error(exc, extra_retryable=extra_retryable):
                raise
            if attempt >= retry.max_attempts:
                logger.warning(
                    "%s failed after %s attempts: %s",
                    operation_name,
                    attempt,
                    type(exc).__name__,
                )
                raise
            delay = retry.delay_for(
                attempt,
                getattr(exc, "retry_after", None)
                if isinstance(exc, ExternalServiceError)
                else None,
            )
            logger.info(
                "%s attempt %s failed (%s); retry in %.3fs",
                operation_name,
                attempt,
                type(exc).__name__,
                delay,
            )
            if on_retry is not None:
                on_retry(attempt, exc, delay)
            await sleep_fn(delay)


async def async_retry_result(
    operation: Callable[[], Awaitable[T]],
    *,
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], Awaitable[None]] | None = None,
    operation_name: str = "operation",
) -> tuple[T | None, RetryOutcome]:
    """Like async_retry but returns (value|None, outcome) instead of raising on exhaustion.

    Still re-raises non-retryable errors immediately.
    """
    retry = policy or RetryPolicy()
    attempts = 0

    async def tracked() -> T:
        nonlocal attempts
        attempts += 1
        return await operation()

    # Wrap to count only actual operation invocations via a custom loop
    sleep_fn = sleep or asyncio.sleep
    attempt = 0
    last_exc: BaseException | None = None
    while True:
        attempt += 1
        try:
            value = await operation()
            return value, RetryOutcome(attempts=attempt, succeeded=True)
        except BaseException as exc:
            last_exc = exc
            if not is_retryable_error(exc):
                raise
            if attempt >= retry.max_attempts:
                return None, RetryOutcome(
                    attempts=attempt, succeeded=False, last_error=exc
                )
            delay = retry.delay_for(
                attempt,
                getattr(exc, "retry_after", None)
                if isinstance(exc, ExternalServiceError)
                else None,
            )
            await sleep_fn(delay)
