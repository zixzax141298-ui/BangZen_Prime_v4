"""Forward paper session: accepted signals -> paper orders -> settlement -> forward ledger.

Paper only. This module calls the existing paper use case and the forward recording helper.
It has no signing, wallet, RPC, or broadcast dependency.

Frozen configuration: the ledger stores the configuration hash it was created with. Opening
an existing ledger with a different hash is refused, so one forward record can never mix
two configurations.

Lifecycle phase: read from token_lifecycle when the order is opened, then stored once in
forward_order_phase (migration 0006). It survives restarts. An order with no stored phase is
labelled UNKNOWN. Phase is never guessed from the close time.
"""

from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from bangzen_prime.core.errors import DomainError
from bangzen_prime.execution.forward_recording import sync_closed_orders
from bangzen_prime.execution.paper_trading import PaperTradingUseCase
from bangzen_prime.research.config_freeze import config_hash
from bangzen_prime.research.forward_paper import ForwardPaperLedger
from bangzen_prime.risk.risk_engine import RiskLimits
from bangzen_prime.storage.database import Database, utc_iso

UNKNOWN_PHASE = "UNKNOWN"


def _plain(value):
    if isinstance(value, timedelta):
        return int(value.total_seconds())
    return value


def paper_config_hash(
    *,
    risk_limits: RiskLimits,
    fee_rate: Decimal,
    slippage_rate: Decimal,
    daily_loss_limit_pct: Decimal,
) -> str:
    """Hash of every setting that changes paper outcomes. Freeze it before forward testing."""
    limits = {f.name: _plain(getattr(risk_limits, f.name)) for f in dataclasses.fields(risk_limits)}
    return config_hash(
        {
            "schema": "forward-paper-config-1",
            "risk_limits": limits,
            "fee_rate": fee_rate,
            "slippage_rate": slippage_rate,
            "daily_loss_limit_pct": daily_loss_limit_pct,
        }
    )


@dataclass(frozen=True)
class SessionCycle:
    opened: tuple[str, ...]
    rejected: tuple[tuple[str, tuple[str, ...]], ...]
    closed: int
    recorded: int


class ForwardPaperSession:
    def __init__(
        self,
        *,
        paper: PaperTradingUseCase,
        db: Database,
        ledger: ForwardPaperLedger,
        ledger_path: str | Path | None = None,
    ) -> None:
        self._paper = paper
        self._db = db
        self._ledger = ledger
        self._path = Path(ledger_path) if ledger_path is not None else None

    @classmethod
    def open(
        cls,
        *,
        paper: PaperTradingUseCase,
        db: Database,
        ledger_path: str | Path,
        config_hash_value: str,
        initial_equity: Decimal,
    ) -> "ForwardPaperSession":
        path = Path(ledger_path)
        if path.exists():
            ledger = ForwardPaperLedger.load(path)
            if ledger.config_hash != config_hash_value:
                raise DomainError(
                    "frozen configuration changed since this forward ledger was started; "
                    "start a new ledger file instead of mixing configurations"
                )
        else:
            ledger = ForwardPaperLedger(config_hash_value, initial_equity)
        return cls(paper=paper, db=db, ledger=ledger, ledger_path=path)

    @property
    def ledger(self) -> ForwardPaperLedger:
        return self._ledger

    def _mint_for_signal(self, signal_id: uuid.UUID) -> str | None:
        row = self._db.query_one(
            "SELECT t.mint AS mint FROM signals s JOIN tokens t ON t.id = s.token_id WHERE s.id = ?",
            (str(signal_id),),
        )
        return row["mint"] if row else None

    def _phase_for_mint(self, mint: str | None) -> str:
        if mint is None:
            return UNKNOWN_PHASE
        row = self._db.query_one(
            "SELECT phase FROM token_lifecycle WHERE chain = 'solana' AND mint = ?", (mint,)
        )
        return row["phase"] if row else UNKNOWN_PHASE

    def _store_phase(self, order_id: str, phase: str) -> None:
        # INSERT OR IGNORE: the phase is captured once, at open, and never rewritten.
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO forward_order_phase (order_id, phase, recorded_at)"
                " VALUES (?, ?, ?)",
                (order_id, phase, utc_iso(datetime.now(UTC))),
            )

    def _phase_of_order(self, order_id: str) -> str:
        row = self._db.query_one(
            "SELECT phase FROM forward_order_phase WHERE order_id = ?", (order_id,)
        )
        return row["phase"] if row else UNKNOWN_PHASE

    def run_once(self, signal_ids: Iterable[uuid.UUID]) -> SessionCycle:
        opened: list[str] = []
        rejected: list[tuple[str, tuple[str, ...]]] = []
        for signal_id in signal_ids:
            phase = self._phase_for_mint(self._mint_for_signal(signal_id))
            outcome = self._paper.open_from_signal(signal_id)
            if outcome.order is not None:
                opened.append(outcome.order.id)
                self._store_phase(outcome.order.id, phase)
            else:
                rejected.append((str(signal_id), tuple(outcome.decision.reasons)))

        closed = self._paper.settle_open_positions()
        recorded = sync_closed_orders(
            self._ledger,
            closed,
            lifecycle_phase=lambda order: self._phase_of_order(order.id),
        )
        if self._path is not None:
            self._ledger.save(self._path)
        return SessionCycle(
            opened=tuple(opened),
            rejected=tuple(rejected),
            closed=len(closed),
            recorded=recorded,
        )
