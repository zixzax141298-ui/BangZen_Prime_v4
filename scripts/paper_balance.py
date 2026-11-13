"""Read-only paper-trading balance and PnL report.

Usage: python3 scripts/paper_balance.py [--db PATH] [--starting-equity AMOUNT]

Reads the paper portfolio from the database and prints equity, peak equity, drawdown,
open positions and realized PnL. It never writes to the database and never places or
signs any transaction. All figures are simulated (paper) and are not real funds.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from bangzen_prime.application.paper_trading import PaperPortfolio  # noqa: E402
from bangzen_prime.infrastructure.persistence.sqlite.database import Database  # noqa: E402
from bangzen_prime.settings import Settings  # noqa: E402


def _decimal(text: str) -> Decimal:
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise argparse.ArgumentTypeError(f"not a number: {text!r}") from exc
    if not value.is_finite() or value <= 0:
        raise argparse.ArgumentTypeError("starting equity must be a positive finite number")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Paper trading balance and PnL (read-only)")
    parser.add_argument("--db", default=None, help="SQLite database path (default: settings db_path)")
    parser.add_argument("--starting-equity", type=_decimal, default=None,
                        help="Starting paper equity (default: settings starting_equity)")
    args = parser.parse_args(argv)

    settings = Settings()
    db_path = args.db or settings.db_path
    if not Path(db_path).is_file():
        print(f"database not found: {db_path}", file=sys.stderr)
        return 1
    starting = args.starting_equity or settings.starting_equity

    db = Database(db_path)
    try:
        snap = PaperPortfolio(db, starting).snapshot(datetime.now(UTC))
        realized = db.query_one(
            "SELECT COALESCE(SUM(CAST(realized_pnl AS REAL)), 0) AS total FROM orders"
            " WHERE status = 'CLOSED' AND realized_pnl IS NOT NULL"
        )
        closed_count = db.query_one(
            "SELECT COUNT(*) AS n FROM orders WHERE status = 'CLOSED'"
        )
    finally:
        db.close()

    equity = snap.equity_quote
    peak = snap.peak_equity_quote
    drawdown = (peak - equity) / peak * Decimal("100") if peak > 0 else Decimal("0")

    print("PAPER TRADING (simulasi, bukan uang sungguhan)")
    print(f"Modal awal        : {starting}")
    print(f"Saldo (ekuitas)   : {equity}")
    print(f"Puncak ekuitas    : {peak}")
    print(f"Drawdown          : {drawdown:.2f}%")
    print(f"Posisi terbuka    : {len(snap.open_positions)}")
    print(f"Trade tertutup    : {closed_count['n']}")
    print(f"PnL terealisasi   : {realized['total']:.4f}")
    print("Catatan: angka ini belum termasuk slippage di luar model simulasi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
