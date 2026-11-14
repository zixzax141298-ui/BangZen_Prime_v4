"""Deterministic paper soak test. Offline, seeded, and self-checking.

Each cycle: scan a seeded random-walk market, deliver the outbox, open paper positions for
accepted signals, and close open positions when the walk reaches stop or target. At the end the
run checks invariants and returns a report. Any violated invariant makes `passed` False.
"""

from __future__ import annotations

import json
import random
import uuid
from decimal import Decimal

from bangzen_prime.application.paper_trading import PaperPortfolio, PaperTradingUseCase
from bangzen_prime.application.risk_engine import (
    ExposureReservations,
    RiskEngine,
    RiskLimits,
)
from bangzen_prime.bootstrap import build_container
from bangzen_prime.infrastructure.adapters.execution.simulated import SimulatedExecution
from bangzen_prime.infrastructure.http import HttpResponse
from bangzen_prime.infrastructure.persistence.sqlite.outbox import AuditLog
from bangzen_prime.infrastructure.resilience.policies import FakeClock
from bangzen_prime.settings import Settings

SOAK_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
SOAK_PAIR = "HxFLKUAmAMLz1jtT3hbvCMELwH5H9tpM2QugP8sKyfhc"


class SeededMarket:
    """Random walk with a seeded RNG. Responds to DexScreener and RugCheck URL shapes."""

    def __init__(self, seed: int) -> None:
        self._rng = random.Random(seed)
        self.price = 1.0
        self.last_pair_price = 1.0

    def step(self) -> None:
        self.price = max(
            0.01, self.price * (1 + self._rng.uniform(-0.045, 0.045))
        )  # zero drift on purpose

    def __call__(self, url: str, timeout: float) -> HttpResponse:
        if "rugcheck" in url:
            return HttpResponse(
                200,
                json.dumps(
                    {"score_normalised": 15, "risks": [], "rugged": False}
                ).encode(),
                {},
            )
        pair = {
            "chainId": "solana",
            "dexId": "raydium",
            "pairAddress": SOAK_PAIR,
            "baseToken": {"address": SOAK_MINT, "symbol": "SOAK"},
            "priceUsd": f"{self.price:.6f}",
            "liquidity": {"usd": 300000.0},
            "volume": {"h24": 500000.0},
        }
        return HttpResponse(200, json.dumps([pair]).encode(), {})


class _Sink:
    def __init__(self) -> None:
        self.count = 0

    def send(self, text: str) -> None:
        self.count += 1


def run_soak(*, cycles: int = 200, seed: int = 7) -> dict:
    if cycles < 1:
        raise ValueError("cycles must be >= 1")
    settings = Settings(db_path=":memory:", starting_equity=Decimal(1000))
    market = SeededMarket(seed)
    sink = _Sink()
    container = build_container(
        settings,
        transport=market,
        notifier=sink,
        db_path=":memory:",
        sleep=lambda s: None,
        clock=FakeClock(),
    )
    limits = RiskLimits(
        max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
        max_open_positions=settings.max_open_positions,
        max_exposure_quote=settings.max_exposure_quote,
        max_drawdown_pct=settings.max_drawdown_pct,
        min_liquidity_usd=settings.min_liquidity_usd,
        max_spread_pct=Decimal(1),
        max_slippage_pct=Decimal(1),
        fee_rate=settings.fee_rate,
        emergency_stop=settings.emergency_stop,
    )
    execution = SimulatedExecution(
        db=container.db,
        fee_rate=settings.fee_rate,
        slippage_rate=settings.slippage_rate,
        clock=container.clock.now,
        paper=True,
        dry_run=True,
    )
    paper = PaperTradingUseCase(
        db=container.db,
        uow=container.uow,
        engine=RiskEngine(limits),
        execution=execution,
        portfolio=PaperPortfolio(container.db, settings.starting_equity),
        reservations=ExposureReservations(settings.max_exposure_quote),
        clock=container.clock.now,
        expected_slippage_pct=settings.slippage_rate * 100,
    )
    opened = closed = 0
    for _ in range(cycles):
        market.step()
        container.scan.execute("solana", [SOAK_MINT])
        container.worker.run_once()
        # Only accepted signals that have no order yet. Re-trying a signal is idempotent anyway,
        # but skipping it keeps the audit trail free of repeated decisions.
        for row in container.db.query_all(
            "SELECT s.id FROM signals s WHERE s.status = 'ACCEPTED' AND NOT EXISTS"
            " (SELECT 1 FROM orders o WHERE o.signal_id = s.id) ORDER BY s.created_at, s.id"
        ):
            outcome = paper.open_from_signal(uuid.UUID(row["id"]))
            if outcome.order is not None:
                opened += 1
        for order in execution.open_orders():
            if (
                execution.on_price(order.id, Decimal(str(round(market.price, 6))))
                is not None
            ):
                closed += 1
        container.clock.advance(60)
    container.worker.run_once()

    # Force-close anything still open at the final price so the books end flat.
    for order in execution.open_orders():
        execution.on_price(order.id, order.stop_loss)
        closed += 1

    snapshot = PaperPortfolio(container.db, settings.starting_equity).snapshot(
        container.clock.now()
    )
    realised_rows = container.db.query_all(
        "SELECT realized_pnl FROM orders WHERE status = 'CLOSED'"
    )
    realised_total = sum(
        (Decimal(r["realized_pnl"]) for r in realised_rows), Decimal(0)
    )
    with container.db.transaction() as conn:
        broken = AuditLog(conn).verify()
    checks = {
        "ledger_reconciles": execution.reconcile() == [],
        "audit_chain_intact": broken is None,
        "no_stuck_outbox_rows": container.db.query_one(
            "SELECT COUNT(*) AS n FROM outbox WHERE status = 'PROCESSING'"
        )["n"]
        == 0,
        "no_dead_letters": container.db.query_one(
            "SELECT COUNT(*) AS n FROM outbox WHERE status = 'FAILED'"
        )["n"]
        == 0,
        "books_flat": snapshot.open_count == 0,
        # With a flat book, equity = start + sum(realised PnL). Summation order differs between
        # PaperPortfolio (sequential) and this check, so Decimal's 28-digit context can differ in
        # the last digits (observed 3E-25). Tolerance is 1E-18 quote; anything larger fails.
        "equity_identity": abs(
            snapshot.equity_quote - (settings.starting_equity + realised_total)
        )
        < Decimal("1E-18"),
        "live_locked": settings.live_trading is False and settings.dry_run is True,
    }
    return {
        "cycles": cycles,
        "seed": seed,
        "accepted_signals": container.db.query_one(
            "SELECT COUNT(*) AS n FROM signals WHERE status='ACCEPTED'"
        )["n"],
        "rejected_signals": container.db.query_one(
            "SELECT COUNT(*) AS n FROM signals WHERE status='REJECTED'"
        )["n"],
        "notifications_delivered": sink.count,
        "orders_opened": opened,
        "orders_closed": closed,
        "final_equity_quote": str(snapshot.equity_quote),
        "checks": checks,
        "passed": all(checks.values()),
    }
