"""Dynamic Jito tip policy. Pure arithmetic, all in lamports (Decimal).

Rules, applied in order:
- The tip never exceeds `share_of_gain` times the expected gain, so a bundle never costs more
  than it may earn.
- The tip never exceeds the absolute cap.
- The resulting tip must clear the market floor. If it cannot, no bundle is priced (DomainError).
"""

from __future__ import annotations

from decimal import Decimal

from bangzen_prime.core.errors import DomainError
from bangzen_prime.core.values import non_negative, positive


def dynamic_tip_lamports(
    *,
    market_floor_lamports: object,
    expected_gain_lamports: object,
    cap_lamports: object,
    share_of_gain: object = Decimal("0.5"),
) -> Decimal:
    floor = non_negative(market_floor_lamports, "market_floor_lamports")
    gain = non_negative(expected_gain_lamports, "expected_gain_lamports")
    cap = positive(cap_lamports, "cap_lamports")
    share = positive(share_of_gain, "share_of_gain")
    if share > 1:
        raise DomainError("share_of_gain must be within (0, 1]")
    gain_limit = gain * share
    if floor > cap:
        raise DomainError("market tip floor is above the cap: no bundle priced")
    tip = min(cap, gain_limit)
    if tip < floor:
        raise DomainError("expected gain and cap cannot clear the market tip floor")
    return tip
