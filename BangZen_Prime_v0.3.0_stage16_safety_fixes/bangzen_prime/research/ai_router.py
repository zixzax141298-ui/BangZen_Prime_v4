"""Ordered AI provider router. One provider is active per call. Failover only on provider-side failure.

The router forwards a completion request and nothing else. It does not own a trading decision,
cannot change the analyst-only contract enforced in ai_brain, and never logs keys.

Failover happens on: quota or key failure (401, 402, 403, 429), model or request rejection that a
different provider may accept (400, 404), server errors (5xx), circuit-open, and transport
failures that are retryable. Any other error is raised unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from bangzen_prime.core.errors import CircuitOpenError, ConfigurationError, ExternalServiceError

FAILOVER_STATUSES = frozenset({400, 401, 402, 403, 404, 429})


class CompletionProvider(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


def _should_failover(exc: ExternalServiceError) -> bool:
    if exc.status is None:
        return exc.retryable
    return exc.status in FAILOVER_STATUSES or exc.status >= 500


class AIRouter:
    name = "router"

    def __init__(self, providers: Sequence[tuple[str, CompletionProvider]]) -> None:
        if not providers:
            raise ConfigurationError("AI router needs at least one configured provider")
        names = [name for name, _ in providers]
        if len(set(names)) != len(names):
            raise ConfigurationError("AI router providers must be unique")
        self._providers = tuple(providers)
        self.last_provider: str | None = None

    @property
    def provider_order(self) -> tuple[str, ...]:
        return tuple(name for name, _ in self._providers)

    def complete(self, system: str, user: str) -> str:
        failures: list[str] = []
        for name, provider in self._providers:
            try:
                text = provider.complete(system, user)
            except CircuitOpenError:
                failures.append(f"{name}:circuit_open")
                continue
            except ExternalServiceError as exc:
                if not _should_failover(exc):
                    raise
                failures.append(f"{name}:{exc.status if exc.status is not None else 'unavailable'}")
                continue
            self.last_provider = name
            return text
        raise ExternalServiceError(
            "all AI providers unavailable (" + ", ".join(failures) + ")",
            service="ai",
            retryable=True,
        )
