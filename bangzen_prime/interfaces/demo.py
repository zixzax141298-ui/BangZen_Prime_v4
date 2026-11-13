"""Offline demo: runs the full paper pipeline against a deterministic in-memory market.

No network is used. The demo proves the pipeline end to end: scan, safety gate, signal,
outbox delivery to a log notifier, paper order, closure, reconciliation, and audit verification.
"""

from __future__ import annotations

import json
from decimal import Decimal

from bangzen_prime.application.ai_brain import AIBrain
from bangzen_prime.application.paper_trading import PaperPortfolio, PaperTradingUseCase
from bangzen_prime.application.risk_engine import ExposureReservations, RiskEngine, RiskLimits
from bangzen_prime.bootstrap import build_container
from bangzen_prime.infrastructure.adapters.execution.simulated import SimulatedExecution
from bangzen_prime.infrastructure.http import HttpResponse
from bangzen_prime.infrastructure.persistence.sqlite.outbox import AuditLog
from bangzen_prime.settings import Settings

DEMO_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
DEMO_PAIR = "HxFLKUAmAMLz1jtT3hbvCMELwH5H9tpM2QugP8sKyfhc"


class OfflineMarket:
    """Deterministic fake for both upstreams. Price rises then wobbles, so signals appear."""

    def __init__(self) -> None:
        self._step = 0

    def __call__(self, url: str, timeout: float) -> HttpResponse:
        if "rugcheck" in url:
            body = {"score_normalised": 12, "risks": [], "rugged": False}
            return HttpResponse(200, json.dumps(body).encode(), {})
        price = 1.0 + 0.01 * self._step + 0.02 * ((self._step % 5) - 2) / 2
        self._step += 1
        pair = {
            "chainId": "solana", "dexId": "raydium", "pairAddress": DEMO_PAIR,
            "baseToken": {"address": DEMO_MINT, "symbol": "DEMO"},
            "pairCreatedAt": 1_700_000_000_000,  # old pair, so the phase is MATURE (labelled offline data)
            "priceUsd": f"{price:.6f}", "liquidity": {"usd": 250000.0},
            "volume": {"h24": 400000.0},
        }
        return HttpResponse(200, json.dumps([pair]).encode(), {})


class _OfflineAI:
    """Offline stand-in for the model. Always answers BUY with high confidence, and says so."""

    name = "offline-demo"

    def complete(self, system: str, user: str) -> str:
        return json.dumps({"decision": "BUY", "confidence": 0.95,
                           "reason": "offline demo stub: not a model judgement"})


class _OfflineHolders:
    def holder_profile(self, chain: str, mint: str):
        from types import SimpleNamespace
        return SimpleNamespace(mint=mint, holder_count=500,
                               top_holder_share_pct=Decimal("18.5"), source="solana_tracker")


class _OfflineIntel:
    async def analyze_token(self, mint: str):
        from types import SimpleNamespace
        return SimpleNamespace(is_bundled=False, has_mev=False, score=Decimal("90"))


class _LogSink:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, text: str) -> None:
        self.messages.append(text)


def run_demo(*, scans: int = 25) -> dict:
    settings = Settings(db_path=":memory:")
    sink = _LogSink()
    container = build_container(settings, transport=OfflineMarket(), notifier=sink,
                                db_path=":memory:", sleep=lambda s: None)
    # Every evidence source is an explicit offline stub, shown in the report below.
    container.scan.ai_brain = AIBrain(_OfflineAI(), threshold=Decimal("0.8"))
    container.scan.holder_data = _OfflineHolders()
    container.scan.intel_adapter = _OfflineIntel()
    for _ in range(scans):
        container.scan.execute("solana", [DEMO_MINT])
    container.worker.run_once()

    limits = RiskLimits(max_risk_per_trade_pct=settings.max_risk_per_trade_pct,
                        max_open_positions=settings.max_open_positions,
                        max_exposure_quote=settings.max_exposure_quote,
                        max_drawdown_pct=settings.max_drawdown_pct,
                        min_liquidity_usd=settings.min_liquidity_usd,
                        max_spread_pct=Decimal("1"), max_slippage_pct=Decimal("1"),
                        fee_rate=settings.fee_rate,
                        emergency_stop=settings.emergency_stop)
    execution = SimulatedExecution(db=container.db, fee_rate=settings.fee_rate,
                                   slippage_rate=settings.slippage_rate, clock=container.clock.now,
                                   paper=True, dry_run=True)
    paper = PaperTradingUseCase(db=container.db, uow=container.uow, engine=RiskEngine(limits),
                                execution=execution,
                                portfolio=PaperPortfolio(container.db, settings.starting_equity),
                                reservations=ExposureReservations(settings.max_exposure_quote),
                                clock=container.clock.now,
                                expected_slippage_pct=settings.slippage_rate * 100)
    opened = None
    row = container.db.query_one("SELECT id FROM signals WHERE status = 'ACCEPTED' LIMIT 1")
    if row is not None:
        import uuid
        opened = paper.open_from_signal(uuid.UUID(row["id"])).order
    closed = None
    if opened is not None:
        closed = execution.on_price(opened.id, opened.take_profit)
    with container.db.transaction() as conn:
        audit_broken_at = AuditLog(conn).verify()
    return {
        "scans": scans,
        "accepted_signals": container.db.query_one(
            "SELECT COUNT(*) AS n FROM signals WHERE status='ACCEPTED'")["n"],
        "rejected_signals": container.db.query_one(
            "SELECT COUNT(*) AS n FROM signals WHERE status='REJECTED'")["n"],
        "notifications_delivered": len(sink.messages),
        "paper_order": opened.status.value if opened else None,
        "paper_order_closed_pnl": str(closed.realized_pnl) if closed else None,
        "ledger_mismatches": execution.reconcile(),
        "audit_chain_broken_at": audit_broken_at,
        "live_trading": settings.live_trading,
    }
