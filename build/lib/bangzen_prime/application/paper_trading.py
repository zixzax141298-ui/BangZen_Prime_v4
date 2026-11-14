"""Paper trading orchestration: accepted signal -> risk decision -> simulated order.

One lock serialises the whole open-position path in this process, so two signals cannot both
pass the exposure check against the same snapshot. Every decision is written to the audit log.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bangzen_prime.application.risk_engine import (
    ExposureReservations,
    RiskDecision,
    RiskEngine,
    TradeRequest,
)
from bangzen_prime.application.token_program_evidence import TokenProgramEvidenceUseCase
from bangzen_prime.domain.risk import OpenPosition, PortfolioSnapshot
from bangzen_prime.domain.signals import SignalStatus
from bangzen_prime.infrastructure.adapters.execution.simulated import (
    OrderCommand,
    OrderRecord,
    SimulatedExecution,
)
from bangzen_prime.infrastructure.persistence.sqlite.database import Database, parse_iso
from bangzen_prime.infrastructure.persistence.sqlite.outbox import AuditLog
from bangzen_prime.infrastructure.persistence.sqlite.repositories import UnitOfWork


@dataclass(frozen=True)
class OpenOutcome:
    decision: RiskDecision
    order: OrderRecord | None


class PaperPortfolio:
    """Builds PortfolioSnapshot from persisted orders. Equity = start + realised - open fees."""

    def __init__(self, db: Database, starting_equity: Decimal) -> None:
        self._db = db
        self._start = starting_equity

    def snapshot(self, now: datetime) -> PortfolioSnapshot:
        closed = self._db.query_all(
            "SELECT realized_pnl, closed_at FROM orders WHERE status = 'CLOSED'"
            " ORDER BY closed_at, id"
        )
        equity = self._start
        peak = self._start
        last_loss: datetime | None = None
        for row in closed:
            equity += Decimal(row["realized_pnl"])
            peak = max(peak, equity)
            if Decimal(row["realized_pnl"]) < 0:
                last_loss = parse_iso(row["closed_at"])
        open_rows = self._db.query_all(
            "SELECT o.filled_units, o.fill_price, o.entry_fee, t.mint FROM orders o"
            " JOIN tokens t ON t.id = o.token_id WHERE o.status IN ('FILLED', 'PARTIALLY_FILLED')"
        )
        positions = []
        for row in open_rows:
            equity -= Decimal(row["entry_fee"])
            positions.append(
                OpenPosition(
                    row["mint"],
                    Decimal(row["filled_units"]),
                    Decimal(row["fill_price"]),
                )
            )
        peak = max(peak, equity)
        return PortfolioSnapshot.create(
            equity_quote=equity,
            peak_equity_quote=peak,
            open_positions=tuple(positions),
            as_of=now,
            last_loss_at=last_loss,
        )


class PaperTradingUseCase:
    def __init__(
        self,
        *,
        db: Database,
        uow: UnitOfWork,
        engine: RiskEngine,
        execution: SimulatedExecution,
        portfolio: PaperPortfolio,
        reservations: ExposureReservations,
        clock: Callable[[], datetime],
        expected_slippage_pct: Decimal,
        halt: Callable[[], bool] | None = None,
        ai_gate: Callable[[TradeRequest], tuple[bool, str]] | None = None,
        token_program_evidence: TokenProgramEvidenceUseCase | None = None,
    ) -> None:
        self._db = db
        self._uow = uow
        self._engine = engine
        self._execution = execution
        self._portfolio = portfolio
        self._reservations = reservations
        self._clock = clock
        self._expected_slippage_pct = expected_slippage_pct
        self._halt = halt or (lambda: False)
        self._ai_gate = ai_gate
        self._token_program_evidence = token_program_evidence
        self._lock = threading.Lock()

    def open_from_signal(self, signal_id: uuid.UUID) -> OpenOutcome:
        with self._lock:
            now = self._clock()
            if self._halt():
                return OpenOutcome(RiskDecision(False, ("EMERGENCY_STOP",), None), None)
            with self._uow.begin() as repos:
                signal = repos.signals.get(signal_id)
            if (
                signal is None
                or signal.status is not SignalStatus.ACCEPTED
                or signal.levels is None
            ):
                return OpenOutcome(
                    RiskDecision(False, ("SIGNAL_NOT_ACCEPTED",), None), None
                )
            pair_rows = self._db.query_all(
                "SELECT t.mint, p.liquidity_usd FROM pairs p JOIN tokens t ON t.id = p.token_id"
                " WHERE p.token_id = ?",
                (str(signal.token_id),),
            )
            if not pair_rows:
                return OpenOutcome(
                    RiskDecision(False, ("MARKET_UNAVAILABLE",), None), None
                )
            best = max(pair_rows, key=lambda r: Decimal(r["liquidity_usd"]))
            token_assessment = (
                self._token_program_evidence.execute(
                    best["mint"],
                    now=now,
                    max_age=self._engine.limits.max_portfolio_age,
                )
                if self._token_program_evidence is not None
                else None
            )
            request = TradeRequest(
                signal_id=signal.id,
                token_id=signal.token_id,
                token_mint=best["mint"],
                levels=signal.levels,
                liquidity_usd=Decimal(best["liquidity_usd"]),
                spread_pct=Decimal(
                    0
                ),  # spread is not part of the pair snapshot; recorded as zero
                slippage_pct=self._expected_slippage_pct,
                token_program=(
                    token_assessment.token_program
                    if token_assessment is not None
                    else None
                ),
            )
            snapshot = self._portfolio.snapshot(now)
            decision = self._engine.evaluate(
                request,
                snapshot,
                now,
                token_program_evidence=(
                    token_assessment.evidence if token_assessment is not None else None
                ),
            )
            self._audit(decision, request, now)
            if not decision.approved or decision.sizing is None:
                return OpenOutcome(decision, None)
            if self._ai_gate is not None:
                allowed, _reason = self._ai_gate(request)
                if not allowed:
                    skipped = RiskDecision(False, ("AI_SKIP",), decision.sizing)
                    self._audit(skipped, request, now)
                    return OpenOutcome(skipped, None)
            amount = decision.sizing.exposure_quote
            if not self._reservations.try_reserve(amount, snapshot.open_exposure_quote):
                denied = RiskDecision(
                    False, ("EXPOSURE_RESERVATION_DENIED",), decision.sizing
                )
                self._audit(denied, request, now)
                return OpenOutcome(denied, None)
            try:
                order = self._execution.submit(
                    OrderCommand(
                        idempotency_key=f"open:{signal.id}",
                        signal_id=signal.id,
                        token_id=signal.token_id,
                        levels=signal.levels,
                        size_units=decision.sizing.size_units,
                        token_mint=request.token_mint,
                    )
                )
            finally:
                self._reservations.release(amount)
            return OpenOutcome(decision, order)

    def _audit(
        self, decision: RiskDecision, request: TradeRequest, now: datetime
    ) -> None:
        with self._db.transaction() as conn:
            AuditLog(conn).append(
                "RiskDecision", decision.as_audit_payload(request), now
            )
