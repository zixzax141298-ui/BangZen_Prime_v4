"""Daily realised-loss check, re-applied when a paper order is opened.

The RiskGovernor checks daily loss when a signal is created. This check repeats the loss
test at order time, because a signal accepted earlier can be executed after the day's loss
limit has been reached.

Fail closed: if today's loss cannot be read, the check returns DAILY_LOSS_UNAVAILABLE and
the order is refused. Unknown is never treated as zero loss.
"""

from __future__ import annotations

from decimal import Decimal

from bangzen_prime.core.errors import DomainError

DAILY_LOSS_LIMIT = "DAILY_LOSS_LIMIT"
DAILY_LOSS_UNAVAILABLE = "DAILY_LOSS_UNAVAILABLE"


def daily_loss_reason(daily_loss_pct: Decimal | None, limit_pct: Decimal) -> str | None:
    """Return a reason code if the order must be refused, otherwise None."""
    if not isinstance(limit_pct, Decimal) or not limit_pct.is_finite():
        raise DomainError("limit_pct must be a finite Decimal")
    if not Decimal(0) < limit_pct <= Decimal(100):
        raise DomainError("limit_pct must be in (0, 100]")
    if daily_loss_pct is None:
        return DAILY_LOSS_UNAVAILABLE
    if not isinstance(daily_loss_pct, Decimal) or not daily_loss_pct.is_finite():
        return DAILY_LOSS_UNAVAILABLE
    if daily_loss_pct < 0:
        raise DomainError("daily_loss_pct must be >= 0 (loss magnitude)")
    if daily_loss_pct >= limit_pct:
        return DAILY_LOSS_LIMIT
    return None
