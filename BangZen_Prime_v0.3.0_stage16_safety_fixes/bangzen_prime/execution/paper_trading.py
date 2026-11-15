"""Paper trading orchestration: accepted signal -> live price -> risk decision -> simulated order.

One lock serialises the whole open-position path in this process, so two signals cannot both
pass the exposure check against the same snapshot. Every decision is written to the audit log.

Fail-closed rules (paper only):
  - No current market price for the token -> reject (never fill at the stale signal price).
  - Current price invalidates the stop/target geometry -> reject.
  - Spread not observed -> reject (RiskEngine reason SPREAD_UNAVAILABLE).
  - Equity is marked to market; an open position without a mark is valued at its stop
    level, the pessimistic exit, so unknown prices cannot hide losses.
"""

from __future__ import annotations

import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from bangzen_prime.core.errors import ConfigurationError, DomainError
from bangzen_prime.execution.simulated import (
    OrderCommand,
    OrderRecord,
    SimulatedExecution,
)
from bangzen_prime.risk.daily_loss import daily_loss_reason
from bangzen_prime.risk.risk import OpenPosition, PortfolioSnapshot
from bangzen_prime.risk.risk_engine import (
    ExposureReservations,
    RiskDecision,
    RiskEngine,
    TradeRequest,
)
from bangzen_prime.scoring.signals import PriceLevels, SignalStatus
from bangzen_prime.security.token_program_evidence import TokenProgramEvidenceUseCase
from bangzen_prime.storage.database import Database, parse_iso
from bangzen_prime.storage.outbox import AuditLog
from bangzen_prime.storage.repositories import UnitOfWork

PriceLookup = Callable[[str], Decimal | None]


@dataclass(frozen=True)
class OpenOutcome:
    decision: RiskDecision
    order: OrderRecord | None


class PaperPortfolio:
    """Builds PortfolioSnapshot from persisted orders.

    equity = start + realised PnL - open entry fees + unrealised PnL (mark to market).
    """

    def __init__(self, db: Database, starting_equity: Decimal) -> None:
        self._db = db
        self._start = starting_equity

    def snapshot(
        self, now: datetime, marks: Mapping[str, Decimal] | None = None
    ) -> PortfolioSnapshot:
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
            "SELECT o.filled_units, o.fill_price, o.entry_fee, o.stop_loss, t.mint"
            " FROM orders o JOIN tokens t ON t.id = o.token_id"
            " WHERE o.status IN ('FILLED', 'PARTIALLY_FILLED')"
        )
        positions = []
        for row in open_rows:
            filled = Decimal(row["filled_units"])
            fill = Decimal(row["fill_price"])
            mint = row["mint"]
            mark = marks.get(mint) if marks is not None else None
            if mark is None:
                mark = Decimal(row["stop_loss"])  # pessimistic: value at the exit level
            equity -= Decimal(row["entry_fee"])
            equity += (mark - fill) * filled
            positions.append(OpenPosition(mint, filled, fill))
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
        token_program_evidence: TokenProgramEvidenceUseCase | None = None,
        price_lookup: PriceLookup | None = None,
        spread_lookup: PriceLookup | None = None,
        daily_loss_provider: Callable[[datetime], Decimal | None] | None = None,
        daily_loss_limit_pct: Decimal = Decimal("1.0"),
    ) -> None:
        # Sizing and execution must use the same slippage, or the risk budget is a lie.
        if expected_slippage_pct != execution.slippage_rate * Decimal(100):
            raise ConfigurationError(
                "expected_slippage_pct must equal the executor slippage (percent)"
            )
        # Checked here so a bad limit fails at start-up, not on the first order.
        daily_loss_reason(Decimal(0), daily_loss_limit_pct)
        self._daily_loss_provider = daily_loss_provider
        self._daily_loss_limit_pct = daily_loss_limit_pct
        self._db = db
        self._uow = uow
        self._engine = engine
        self._execution = execution
        self._portfolio = portfolio
        self._reservations = reservations
        self._clock = clock
        self._expected_slippage_pct = expected_slippage_pct
        self._halt = halt or (lambda: False)
        self._token_program_evidence = token_program_evidence
        self._price_lookup = price_lookup
        self._spread_lookup = spread_lookup
        self._lock = threading.Lock()

    def settle_open_positions(self) -> list[OrderRecord]:
        """Close open paper orders whose stop or target is hit at the current market price.

        A position whose price is unknown stays open. Closing on a guessed price would book
        a PnL nobody observed.
        """
        if self._price_lookup is None:
            return []
        closed: list[OrderRecord] = []
        for order in self._execution.open_orders():
            price = self._price_lookup(order.token_mint)
            if price is None or price <= 0:
                continue
            result = self._execution.on_price(order.id, price)
            if result is not None:
                closed.append(result)
        return closed

    def mark_snapshot(self, now: datetime) -> PortfolioSnapshot:
        """Equity and drawdown at current market marks (used by callers and the engine)."""
        return self._portfolio.snapshot(now, self._marks())

    def _marks(self) -> dict[str, Decimal]:
        if self._price_lookup is None:
            return {}
        marks: dict[str, Decimal] = {}
        for row in self._db.query_all(
            "SELECT DISTINCT t.mint FROM orders o JOIN tokens t ON t.id = o.token_id"
            " WHERE o.status IN ('FILLED', 'PARTIALLY_FILLED')"
        ):
            price = self._price_lookup(row["mint"])
            if price is not None and price > 0:
                marks[row["mint"]] = price
        return marks

    def _reject(
        self, reason: str, request_signal_id: uuid.UUID, now: datetime, sizing=None
    ) -> OpenOutcome:
        decision = RiskDecision(False, (reason,), sizing)
        self._audit_decision(decision, request_signal_id, now)
        return OpenOutcome(decision, None)

    def open_from_signal(self, signal_id: uuid.UUID) -> OpenOutcome:
        with self._lock:
            now = self._clock()
            if self._halt():
                return OpenOutcome(RiskDecision(False, ("EMERGENCY_STOP",), None), None)
            if self._daily_loss_provider is not None:
                # Unreadable loss is passed on as None and refused, never treated as zero.
                try:
                    loss_pct = self._daily_loss_provider(now)
                except Exception:  # noqa: BLE001 - fail closed on any provider error
                    loss_pct = None
                reason = daily_loss_reason(loss_pct, self._daily_loss_limit_pct)
                if reason is not None:
                    return OpenOutcome(RiskDecision(False, (reason,), None), None)
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
                return self._reject("MARKET_UNAVAILABLE", signal_id, now)
            best = max(pair_rows, key=lambda r: Decimal(r["liquidity_usd"]))
            mint = best["mint"]

            # Fill at the price that exists now, never at the price when the signal fired.
            price = self._price_lookup(mint) if self._price_lookup else None
            if price is None or price <= 0:
                return self._reject("MARKET_PRICE_UNAVAILABLE", signal_id, now)
            try:
                levels = PriceLevels(
                    price, signal.levels.stop_loss, signal.levels.take_profit
                )
            except DomainError:
                return self._reject("LEVELS_INVALIDATED_AT_MARKET", signal_id, now)

            spread = self._spread_lookup(mint) if self._spread_lookup else None

            token_assessment = (
                self._token_program_evidence.execute(
                    mint,
                    now=now,
                    max_age=self._engine.limits.max_portfolio_age,
                )
                if self._token_program_evidence is not None
                else None
            )
            request = TradeRequest(
                signal_id=signal.id,
                token_id=signal.token_id,
                token_mint=mint,
                levels=levels,
                liquidity_usd=Decimal(best["liquidity_usd"]),
                spread_pct=spread,
                slippage_pct=self._expected_slippage_pct,
                token_program=(
                    token_assessment.token_program
                    if token_assessment is not None
                    else None
                ),
            )
            snapshot = self._portfolio.snapshot(now, self._marks())
            decision = self._engine.evaluate(
                request,
                snapshot,
                now,
                token_program_evidence=(
                    token_assessment.evidence if token_assessment is not None else None
                ),
            )
            self._audit_decision(decision, signal_id, now, request)
            if not decision.approved or decision.sizing is None:
                return OpenOutcome(decision, None)
            amount = decision.sizing.exposure_quote
            if not self._reservations.try_reserve(amount, snapshot.open_exposure_quote):
                denied = RiskDecision(
                    False, ("EXPOSURE_RESERVATION_DENIED",), decision.sizing
                )
                self._audit_decision(denied, signal_id, now, request)
                return OpenOutcome(denied, None)
            try:
                order = self._execution.submit(
                    OrderCommand(
                        idempotency_key=f"open:{signal.id}",
                        signal_id=signal.id,
                        token_id=signal.token_id,
                        levels=levels,
                        size_units=decision.sizing.size_units,
                        token_mint=mint,
                    )
                )
            finally:
                self._reservations.release(amount)
            return OpenOutcome(decision, order)

    def _audit_decision(
        self,
        decision: RiskDecision,
        signal_id: uuid.UUID,
        now: datetime,
        request: TradeRequest | None = None,
    ) -> None:
        payload = (
            decision.as_audit_payload(request)
            if request is not None
            else {
                "signal_id": str(signal_id),
                "approved": decision.approved,
                "reasons": list(decision.reasons),
                "size_units": None,
                "risk_amount_quote": None,
                "exposure_quote": None,
            }
        )
        with self._db.transaction() as conn:
            AuditLog(conn).append("RiskDecision", payload, now)
