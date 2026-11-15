"""Simulated execution (dry-run / paper). There is no signing, RPC, or broadcast code here.

Behaviour:
- Idempotent submit: the same idempotency key always returns the first recorded order.
- Fill model: buy fills at entry * (1 + slippage); fee = fee_rate * notional per side.
- Fault injection (FaultPlan) produces REJECTED, TIMEOUT, or PARTIALLY_FILLED outcomes.
- Stop-loss is a stop-market order: a gap through the stop fills at the actual price,
  not at the stop level, then pays slippage. Take-profit is a limit order: it fills at
  the target (never better), then pays slippage.
- Every money movement is a ledger row; reconcile() checks ledger sums against realized PnL.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bangzen_prime.core.errors import ConfigurationError, DomainError
from bangzen_prime.core.values import non_negative, positive
from bangzen_prime.execution.orders import OPEN_STATUSES, OrderStatus, transition
from bangzen_prime.scoring.signals import PriceLevels
from bangzen_prime.storage.database import (
    Database,
    parse_iso,
    utc_iso,
)


@dataclass(frozen=True)
class OrderCommand:
    idempotency_key: str
    signal_id: uuid.UUID
    token_id: uuid.UUID
    levels: PriceLevels
    size_units: Decimal
    token_mint: str


@dataclass(frozen=True)
class FaultPlan:
    reject: bool = False
    timeout: bool = False
    partial_ratio: Decimal | None = None  # fraction in (0, 1) of requested units


@dataclass(frozen=True)
class OrderRecord:
    id: str
    idempotency_key: str
    signal_id: str
    token_id: str
    token_mint: str
    status: OrderStatus
    requested_units: Decimal
    filled_units: Decimal
    entry_price: Decimal
    fill_price: Decimal | None
    stop_loss: Decimal
    take_profit: Decimal
    entry_fee: Decimal
    exit_price: Decimal | None
    exit_fee: Decimal | None
    realized_pnl: Decimal | None
    created_at: datetime
    closed_at: datetime | None


class SimulatedExecution:
    def __init__(
        self,
        *,
        db: Database,
        fee_rate: Decimal,
        slippage_rate: Decimal,
        clock: Callable[[], datetime],
        paper: bool,
        dry_run: bool,
        faults: FaultPlan | None = None,
    ) -> None:
        if not paper or not dry_run:
            raise ConfigurationError(
                "simulated execution requires paper=True and dry_run=True"
            )
        self._db = db
        self._fee = non_negative(fee_rate, "fee_rate")
        self._slip = non_negative(slippage_rate, "slippage_rate")
        self._clock = clock
        self._faults = faults or FaultPlan()
        if self._faults.partial_ratio is not None and not (
            Decimal(0) < self._faults.partial_ratio < Decimal(1)
        ):
            raise DomainError("partial_ratio must be within (0, 1)")

    @property
    def slippage_rate(self) -> Decimal:
        return self._slip

    @property
    def fee_rate(self) -> Decimal:
        return self._fee

    def submit(self, cmd: OrderCommand) -> OrderRecord:
        size = positive(cmd.size_units, "size_units")
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE idempotency_key = ?", (cmd.idempotency_key,)
            ).fetchone()
            if row is not None:
                return _to_record(row, cmd.token_mint)
            now = self._clock()
            status, filled = self._decide_fill(size)
            fill_price = None
            entry_fee = Decimal(0)
            if filled > 0:
                fill_price = cmd.levels.entry * (Decimal(1) + self._slip)
                entry_fee = self._fee * fill_price * filled
            order_id = str(uuid.uuid4())
            conn.execute(
                "INSERT INTO orders (id, idempotency_key, signal_id, token_id, status,"
                " requested_units, filled_units, entry_price, fill_price, stop_loss, take_profit,"
                " entry_fee, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    order_id,
                    cmd.idempotency_key,
                    str(cmd.signal_id),
                    str(cmd.token_id),
                    status.value,
                    str(size),
                    str(filled),
                    str(cmd.levels.entry),
                    str(fill_price) if fill_price is not None else None,
                    str(cmd.levels.stop_loss),
                    str(cmd.levels.take_profit),
                    str(entry_fee),
                    utc_iso(now),
                ),
            )
            if entry_fee:
                conn.execute(
                    "INSERT INTO ledger_entries (order_id, kind, amount_quote, created_at)"
                    " VALUES (?, 'ENTRY_FEE', ?, ?)",
                    (order_id, str(-entry_fee), utc_iso(now)),
                )
            row = conn.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            return _to_record(row, cmd.token_mint)

    def _decide_fill(self, size: Decimal) -> tuple[OrderStatus, Decimal]:
        if self._faults.reject:
            return OrderStatus.REJECTED, Decimal(0)
        if self._faults.timeout:
            return OrderStatus.TIMEOUT, Decimal(0)
        if self._faults.partial_ratio is not None:
            return OrderStatus.PARTIALLY_FILLED, size * self._faults.partial_ratio
        return OrderStatus.FILLED, size

    def on_price(self, order_id: str, price: Decimal) -> OrderRecord | None:
        """Close an open order if `price` has reached stop-loss or take-profit. Else no-op."""
        price = positive(price, "price")
        with self._db.transaction() as conn:
            row = conn.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            if row is None:
                raise DomainError("unknown order")
            current = OrderStatus(row["status"])
            if current not in OPEN_STATUSES:
                return None
            stop, target = Decimal(row["stop_loss"]), Decimal(row["take_profit"])
            if price <= stop:
                raw_exit = min(price, stop)  # gap-through fills at the real price
            elif price >= target:
                raw_exit = target
            else:
                return None
            exit_price = raw_exit * (Decimal(1) - self._slip)
            filled = Decimal(row["filled_units"])
            fill_price = Decimal(row["fill_price"])
            gross = (exit_price - fill_price) * filled
            exit_fee = self._fee * exit_price * filled
            pnl = gross - Decimal(row["entry_fee"]) - exit_fee
            now = self._clock()
            transition(current, OrderStatus.CLOSED)
            conn.execute(
                "UPDATE orders SET status = 'CLOSED', exit_price = ?, exit_fee = ?, realized_pnl = ?,"
                " closed_at = ? WHERE id = ?",
                (str(exit_price), str(exit_fee), str(pnl), utc_iso(now), order_id),
            )
            conn.execute(
                "INSERT INTO ledger_entries (order_id, kind, amount_quote, created_at)"
                " VALUES (?, 'REALIZED_PNL', ?, ?)",
                (order_id, str(gross), utc_iso(now)),
            )
            conn.execute(
                "INSERT INTO ledger_entries (order_id, kind, amount_quote, created_at)"
                " VALUES (?, 'EXIT_FEE', ?, ?)",
                (order_id, str(-exit_fee), utc_iso(now)),
            )
            updated = conn.execute(
                "SELECT * FROM orders WHERE id = ?", (order_id,)
            ).fetchone()
            return _to_record(updated, None)

    def open_orders(self) -> list[OrderRecord]:
        rows = self._db.query_all(
            "SELECT o.*, t.mint AS mint FROM orders o JOIN tokens t ON t.id = o.token_id"
            " WHERE o.status IN ('FILLED', 'PARTIALLY_FILLED') ORDER BY o.created_at, o.id"
        )
        return [_to_record(r, r["mint"]) for r in rows]

    def get(self, order_id: str) -> OrderRecord | None:
        row = self._db.query_one(
            "SELECT o.*, t.mint AS mint FROM orders o JOIN tokens t ON t.id = o.token_id"
            " WHERE o.id = ?",
            (order_id,),
        )
        return _to_record(row, row["mint"]) if row else None

    def reconcile(self) -> list[str]:
        """Return human-readable mismatches. An empty list means the ledger is consistent."""
        problems: list[str] = []
        rows = self._db.query_all("SELECT * FROM orders")
        for row in rows:
            entries = self._db.query_all(
                "SELECT kind, amount_quote FROM ledger_entries WHERE order_id = ?",
                (row["id"],),
            )
            total = sum((Decimal(e["amount_quote"]) for e in entries), Decimal(0))
            if row["status"] == "CLOSED":
                if total != Decimal(row["realized_pnl"]):
                    problems.append(
                        f"order {row['id']}: ledger {total} != pnl {row['realized_pnl']}"
                    )
            else:
                expected = -Decimal(row["entry_fee"])
                if total != expected:
                    problems.append(
                        f"order {row['id']}: open ledger {total} != entry fee {expected}"
                    )
        return problems


def _to_record(row, mint: str | None) -> OrderRecord:
    def opt_dec(value):
        return Decimal(value) if value is not None else None

    return OrderRecord(
        id=row["id"],
        idempotency_key=row["idempotency_key"],
        signal_id=row["signal_id"],
        token_id=row["token_id"],
        token_mint=mint or "",
        status=OrderStatus(row["status"]),
        requested_units=Decimal(row["requested_units"]),
        filled_units=Decimal(row["filled_units"]),
        entry_price=Decimal(row["entry_price"]),
        fill_price=opt_dec(row["fill_price"]),
        stop_loss=Decimal(row["stop_loss"]),
        take_profit=Decimal(row["take_profit"]),
        entry_fee=Decimal(row["entry_fee"]),
        exit_price=opt_dec(row["exit_price"]),
        exit_fee=opt_dec(row["exit_fee"]),
        realized_pnl=opt_dec(row["realized_pnl"]),
        created_at=parse_iso(row["created_at"]),
        closed_at=parse_iso(row["closed_at"]) if row["closed_at"] else None,
    )
