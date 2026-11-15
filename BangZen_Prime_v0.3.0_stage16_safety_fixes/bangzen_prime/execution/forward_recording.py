"""Copy closed paper orders into the forward paper ledger.

Paper only. This module reads closed simulated orders and writes ForwardTrade rows. It never
opens, changes, or signs an order. Research code (research/forward_paper.py) stays free of
execution imports; the dependency points one way, from here into research.

Rules:
- Only CLOSED orders are recorded. An open order is not a result.
- An order missing any field needed for PnL is refused, never recorded with zeros.
- realized_pnl from SimulatedExecution is already net of entry and exit fees.
- Lifecycle phase is not stored on the order, so it is recorded as "UNKNOWN" unless the caller
  supplies it. The caller must not guess it.
- Syncing is idempotent: an order already in the ledger is skipped, not recorded twice.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from decimal import Decimal

from bangzen_prime.core.errors import DomainError
from bangzen_prime.execution.orders import OrderStatus
from bangzen_prime.execution.simulated import OrderRecord
from bangzen_prime.research.forward_paper import ForwardPaperLedger, ForwardTrade

HUNDRED = Decimal(100)


def forward_trade_from_order(
    order: OrderRecord, lifecycle_phase: str = "UNKNOWN"
) -> ForwardTrade:
    if order.status != OrderStatus.CLOSED:
        raise DomainError(f"order {order.id} is not CLOSED; only closed orders are recorded")
    missing = [
        name
        for name in ("realized_pnl", "exit_price", "fill_price", "closed_at")
        if getattr(order, name) is None
    ]
    if missing:
        raise DomainError(f"order {order.id} lacks {', '.join(missing)}; refusing to record")
    if order.filled_units <= 0:
        raise DomainError(f"order {order.id} has no filled units")
    notional = order.filled_units * order.fill_price
    if notional <= 0:
        raise DomainError(f"order {order.id} has non-positive notional")
    if order.exit_price <= order.stop_loss:
        exit_reason = "STOP_LOSS"
    elif order.exit_price >= order.take_profit:
        exit_reason = "TAKE_PROFIT"
    else:
        exit_reason = "OTHER"
    return ForwardTrade(
        trade_id=order.id,
        lifecycle_phase=lifecycle_phase,
        opened_at=order.created_at,
        closed_at=order.closed_at,
        notional=notional,
        net_pnl=order.realized_pnl,
        net_return_pct=order.realized_pnl / notional * HUNDRED,
        exit_reason=exit_reason,
    )


def sync_closed_orders(
    ledger: ForwardPaperLedger,
    orders: Iterable[OrderRecord],
    lifecycle_phase: str | Callable[[OrderRecord], str] = "UNKNOWN",
) -> int:
    """Record every closed order not yet in the ledger. Returns the number recorded.

    ``lifecycle_phase`` may be a fixed name or a function of the order.
    """
    recorded_ids = {entry.trade.trade_id for entry in ledger.entries}
    count = 0
    for order in orders:
        if order.status != OrderStatus.CLOSED or order.id in recorded_ids:
            continue
        phase = lifecycle_phase(order) if callable(lifecycle_phase) else lifecycle_phase
        trade = forward_trade_from_order(order, phase)
        ledger.record(trade, ledger.config_hash)
        recorded_ids.add(order.id)
        count += 1
    return count
