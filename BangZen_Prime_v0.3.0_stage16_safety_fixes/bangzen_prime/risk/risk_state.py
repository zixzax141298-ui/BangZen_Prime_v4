"""Live portfolio state for the global RiskGovernor, read from persisted paper orders.

The governor previously received hardcoded zeros, so its limits never fired. This reader
supplies the real values. Equity here is starting equity plus realised PnL (conservative:
unrealised gains are not counted, unrealised risk of open positions is).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from bangzen_prime.storage.database import Database, utc_iso

ZERO = Decimal(0)


@dataclass(frozen=True)
class RiskState:
    open_positions: int
    signals_today: int
    portfolio_risk_pct: Decimal
    daily_loss_pct: Decimal


class DbRiskStateReader:
    def __init__(self, db: Database, starting_equity: Decimal) -> None:
        if starting_equity <= 0:
            raise ValueError("starting_equity must be positive")
        self._db = db
        self._start = starting_equity

    def read(self, now: datetime) -> RiskState:
        now = now.astimezone(UTC)
        day_start = utc_iso(datetime(now.year, now.month, now.day, tzinfo=UTC))

        open_rows = self._db.query_all(
            "SELECT filled_units, fill_price, stop_loss FROM orders"
            " WHERE status IN ('FILLED', 'PARTIALLY_FILLED')"
        )
        open_risk = ZERO
        for row in open_rows:
            filled = Decimal(row["filled_units"])
            fill = Decimal(row["fill_price"])
            stop = Decimal(row["stop_loss"])
            open_risk += max(ZERO, (fill - stop) * filled)

        closed = self._db.query_all(
            "SELECT realized_pnl, closed_at FROM orders WHERE status = 'CLOSED'"
        )
        realised_total = ZERO
        realised_today = ZERO
        for row in closed:
            pnl = Decimal(row["realized_pnl"])
            realised_total += pnl
            if row["closed_at"] >= day_start:
                realised_today += pnl

        signals_today = self._db.query_one(
            "SELECT COUNT(*) AS n FROM signals WHERE status = 'ACCEPTED' AND created_at >= ?",
            (day_start,),
        )["n"]
        open_count = self._db.query_one(
            "SELECT COUNT(*) AS n FROM orders WHERE status IN ('FILLED', 'PARTIALLY_FILLED')"
        )["n"]

        equity = self._start + realised_total
        if equity <= 0:
            # Account is wiped out: express every limit as breached.
            return RiskState(open_count, signals_today, Decimal(100), Decimal(100))
        return RiskState(
            open_positions=open_count,
            signals_today=signals_today,
            portfolio_risk_pct=open_risk / equity * Decimal(100),
            daily_loss_pct=max(ZERO, -realised_today) / equity * Decimal(100),
        )


def daily_loss_provider(reader: DbRiskStateReader):
    """Adapter for PaperTradingUseCase: today's loss %, or None if it cannot be read."""
    import logging

    logger = logging.getLogger("bangzen_prime.risk")

    def provide(now: datetime) -> Decimal | None:
        try:
            return reader.read(now).daily_loss_pct
        except Exception as exc:  # noqa: BLE001 - unknown is passed on, never zero
            logger.warning("daily loss unreadable: %s", type(exc).__name__)
            return None

    return provide
