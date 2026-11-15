"""Fail-closed honeypot check adapter.

A token is only reported as safe when the dynamic-tax check completed and returned
an explicit boolean False. Cache skips, malformed provider responses, and provider
errors are UNAVAILABLE; they must never be interpreted as a clean result.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from bangzen_prime.discovery.tokens import validate_mint


@dataclass(frozen=True)
class HoneypotReport:
    is_honeypot: bool | None
    reason: str
    checked_at: datetime
    available: bool

    @property
    def is_safe(self) -> bool:
        """True only for a completed, explicit negative honeypot check."""
        return self.available and self.is_honeypot is False and self.reason == "safe"


class HoneypotAdapter:
    def __init__(
        self,
        jupiter_client: Any,
        clock: Callable[[], datetime],
        check_interval_sec: int = 300,
    ) -> None:
        if isinstance(check_interval_sec, bool) or not isinstance(
            check_interval_sec, int
        ):
            raise ValueError("check_interval_sec must be an integer")
        if check_interval_sec < 1:
            raise ValueError("check_interval_sec must be positive")
        if not callable(clock):
            raise ValueError("clock must be callable")
        if not callable(getattr(jupiter_client, "check_dynamic_tax", None)):
            raise ValueError("jupiter_client must implement check_dynamic_tax")

        self.jupiter = jupiter_client
        self.clock = clock
        self.check_interval_sec = check_interval_sec
        self._last_check: dict[str, float] = {}

    async def check_honeypot(
        self,
        token_address: str,
        force: bool = False,
    ) -> HoneypotReport:
        mint = validate_mint(token_address)
        checked_at = self.clock()
        now = checked_at.timestamp()
        last_check = self._last_check.get(mint, 0.0)

        if not force and now - last_check < self.check_interval_sec:
            return HoneypotReport(
                is_honeypot=None,
                reason="check_not_repeated_cache_window",
                checked_at=checked_at,
                available=False,
            )

        try:
            tax_state = await self.jupiter.check_dynamic_tax(mint)
        except Exception as exc:
            # Do not cache failures: a transient outage must be eligible for retry.
            return HoneypotReport(
                is_honeypot=None,
                reason=f"provider_error_{type(exc).__name__}",
                checked_at=self.clock(),
                available=False,
            )

        if not isinstance(tax_state, bool):
            return HoneypotReport(
                is_honeypot=None,
                reason="provider_response_invalid",
                checked_at=self.clock(),
                available=False,
            )

        # Cache only completed, well-formed checks.
        self._last_check[mint] = now
        return HoneypotReport(
            is_honeypot=tax_state,
            reason="tax_increase_detected" if tax_state else "safe",
            checked_at=checked_at,
            available=True,
        )
