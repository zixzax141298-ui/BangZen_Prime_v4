import unittest
import uuid
from datetime import timedelta
from decimal import Decimal

from bangzen_prime.application.ai_brain import AIBrain, TradeContext, ai_gate
from bangzen_prime.application.heartbeat import (
    EmergencyLatch,
    HeartbeatRegistry,
    Watchdog,
)
from bangzen_prime.application.paper_trading import PaperPortfolio, PaperTradingUseCase
from bangzen_prime.application.risk_engine import (
    ExposureReservations,
    RiskEngine,
    RiskLimits,
)
from bangzen_prime.application.supervisor import Supervisor, WorkerSpec
from bangzen_prime.bootstrap import build_intel_stack
from bangzen_prime.infrastructure.adapters.execution.simulated import SimulatedExecution
from bangzen_prime.infrastructure.observability.metrics import Metrics
from bangzen_prime.settings import Settings
from tests.e2e.test_scan_flow import World, build
from tests.support import START, TOKEN_MINT, json_response

D = Decimal


def paper_uc(container, latch=None, gate=None):
    s = container.settings
    limits = RiskLimits(
        max_risk_per_trade_pct=s.max_risk_per_trade_pct,
        max_open_positions=3,
        max_exposure_quote=s.max_exposure_quote,
        max_drawdown_pct=s.max_drawdown_pct,
        min_liquidity_usd=s.min_liquidity_usd,
        max_spread_pct=D(1),
        max_slippage_pct=D(1),
        fee_rate=s.fee_rate,
    )
    ex = SimulatedExecution(
        db=container.db,
        fee_rate=s.fee_rate,
        slippage_rate=s.slippage_rate,
        clock=container.clock.now,
        paper=True,
        dry_run=True,
    )
    return PaperTradingUseCase(
        db=container.db,
        uow=container.uow,
        engine=RiskEngine(limits),
        execution=ex,
        portfolio=PaperPortfolio(container.db, s.starting_equity),
        reservations=ExposureReservations(s.max_exposure_quote),
        clock=container.clock.now,
        expected_slippage_pct=D("0.5"),
        halt=((lambda: latch.is_active) if latch else None),
        ai_gate=gate,
        token_program_evidence=container.token_program_evidence,
    )


class WatchdogHaltTest(unittest.TestCase):
    def accepted_signal(self):
        c, _, _, clock = build(world=World(), settings=Settings())
        for _ in range(20):
            clock.advance(
                91
            )  # past the 90 s dedupe cooldown so each scan adds a price sample
            c.scan.execute("solana", [TOKEN_MINT])
        row = c.db.query_one("SELECT id FROM signals WHERE status='ACCEPTED' LIMIT 1")
        self.assertIsNotNone(row)
        return c, uuid.UUID(row["id"])

    def test_stale_worker_halts_new_paper_positions(self):
        c, sig = self.accepted_signal()
        latch = EmergencyLatch(audit=lambda e, p, at: None)
        reg = HeartbeatRegistry()
        reg.beat("ingest", START)
        wd = Watchdog(
            registry=reg,
            expected=("ingest",),
            timeout=timedelta(seconds=5),
            latch=latch,
        )
        uc = paper_uc(c, latch=latch)
        self.assertTrue(uc.open_from_signal(sig).decision.approved)
        # a worker goes silent for more than 5 seconds
        self.assertEqual(wd.check(START + timedelta(seconds=6)), ["ingest"])
        self.assertTrue(latch.is_active)
        outcome = uc.open_from_signal(sig)
        self.assertEqual(outcome.decision.reasons, ("EMERGENCY_STOP",))
        self.assertIsNone(outcome.order)

    def test_operator_reset_restores_trading(self):
        c, sig = self.accepted_signal()
        latch = EmergencyLatch()
        latch.trigger("manual", START)
        uc = paper_uc(c, latch=latch)
        self.assertFalse(uc.open_from_signal(sig).decision.approved)
        latch.reset(operator="owner", at=START)
        self.assertTrue(uc.open_from_signal(sig).decision.approved)


class AIGateFlowTest(unittest.TestCase):
    class Provider:
        name = "fake"

        def __init__(self, reply):
            self.reply = reply
            self.calls = 0

        def complete(self, system, user):
            self.calls += 1
            return self.reply

    def test_skip_recommendation_blocks_order(self):
        c, _, _, clock = build(world=World(), settings=Settings())
        for _ in range(20):
            clock.advance(
                91
            )  # past the 90 s dedupe cooldown so each scan adds a price sample
            c.scan.execute("solana", [TOKEN_MINT])
        sig = uuid.UUID(
            c.db.query_one("SELECT id FROM signals WHERE status='ACCEPTED' LIMIT 1")[
                "id"
            ]
        )
        provider = self.Provider(
            '{"decision":"SKIP","confidence":0.9,"reason":"wash trading suspected"}'
        )
        brain = AIBrain(provider, threshold=D("0.6"))

        def ctx_for(request):
            return TradeContext(
                mint=TOKEN_MINT,
                symbol="T",
                liquidity_usd=request.liquidity_usd,
                volume_24h_usd=D(0),
                top_holder_share_pct=None,
                holder_count=None,
                heuristic_score=D(50),
                safety_risk_score=D(10),
                rugged=False,
            )

        uc = paper_uc(c, gate=ai_gate(brain, ctx_for))
        outcome = uc.open_from_signal(sig)
        self.assertEqual(outcome.decision.reasons, ("AI_SKIP",))
        self.assertIsNone(outcome.order)
        self.assertEqual(
            provider.calls, 0
        )  # Missing holder evidence blocks before model inference
        audit = c.db.query_all(
            "SELECT payload FROM audit_log WHERE event_type='RiskDecision'"
        )
        self.assertTrue(any("AI_SKIP" in row["payload"] for row in audit))


class SupervisorHeartbeatTest(unittest.TestCase):
    def test_successful_cycles_feed_the_registry(self):
        reg = HeartbeatRegistry()
        clock_now = {"t": START}
        sup = Supervisor(
            workers=[WorkerSpec("outbox", lambda: None)],
            emergency_stop=lambda: False,
            metrics=Metrics(),
            sleep=lambda s: None,
            beat=lambda name: reg.beat(name, clock_now["t"]),
        )
        sup.run_cycle()
        self.assertEqual(reg.last("outbox"), START)

    def test_failing_worker_does_not_beat(self):
        reg = HeartbeatRegistry()

        def boom():
            raise RuntimeError("x")

        sup = Supervisor(
            workers=[WorkerSpec("outbox", boom)],
            emergency_stop=lambda: False,
            metrics=Metrics(),
            sleep=lambda s: None,
            beat=lambda name: reg.beat(name, START),
        )
        sup.run_cycle()
        self.assertIsNone(reg.last("outbox"))


class IntelStackTest(unittest.TestCase):
    def test_construction_performs_no_network_io(self):
        calls = []

        def transport(request):
            calls.append(request)
            return json_response({})

        stack = build_intel_stack(
            Settings(
                birdeye_api_key="BKEY",
                helius_api_key="HKEY",
                jupiter_api_key="JKEY",
                solana_tracker_api_key="SKEY",
            ),
            transport=transport,
        )
        self.assertEqual(calls, [])  # building adapters must not touch the network
        self.assertIsNotNone(stack.birdeye)
        self.assertIsNotNone(stack.jupiter)
        self.assertIsNotNone(stack.helius)
        self.assertIsNotNone(stack.solana_tracker)
        self.assertIsNone(stack.ai_brain)

    def test_missing_keys_leave_adapters_absent(self):
        stack = build_intel_stack(Settings(), transport=lambda req: None)
        self.assertIsNone(stack.birdeye)
        self.assertTrue(type(stack.jupiter).__name__ == "_NullJupiter")
        self.assertIsNotNone(stack.jito)  # public read-only endpoints need no key

    def test_ai_enabled_builds_selected_provider(self):
        stack = build_intel_stack(
            Settings(ai_enabled=True, ai_provider="openai", openai_api_key="OAIKEY"),
            transport=lambda req: None,
        )
        self.assertIsNotNone(stack.ai_brain)
        self.assertEqual(stack.ai_brain._provider.name, "openai")


if __name__ == "__main__":
    unittest.main()
