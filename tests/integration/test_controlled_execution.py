import unittest
from datetime import timedelta
from decimal import Decimal

from bangzen_prime.application.ai_brain import AIDecision
from bangzen_prime.application.controlled_execution import ChainPolicy, ControlledExecution, SafetyApproval
from bangzen_prime.domain.execution import balance_delta_matches
from bangzen_prime.errors import DomainError
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.infrastructure.persistence.sqlite.repositories import UnitOfWork
from tests.support import START, clock_at
from tests.support_chain import MINTS, OWNER, PROGRAM, VAULT, FakeBuilder, FakeQuotes, FakeRpc, FakeSigner

D = Decimal


def make(quotes=None, builder=None, rpc=None, signer=None, clock=None, allow=False, ai_approved=True, ai_source="model", ai_confidence=D("0.9"), ai_gate_configured=True, risk_gate_configured=True, risk_approved=True, db=None):
    db = db or Database(":memory:")
    db.migrate()
    clock = clock or clock_at(0)
    quotes = quotes or FakeQuotes()
    builder = builder or FakeBuilder()
    builder.now = clock.now()
    quotes.now = clock.now()
    policy = ChainPolicy(owner=OWNER, allowed_programs=frozenset({PROGRAM}),
                         allowed_destinations=frozenset({VAULT}), max_price_impact_pct=D("1"))
    ce = ControlledExecution(uow=UnitOfWork(db), quotes=quotes, builder=builder,
                             rpc=rpc or FakeRpc(), signer=signer or FakeSigner(), policy=policy,
                             clock=clock.now, broadcast_allowed=allow,
                             pretrade_gate=((lambda _i, _o, _a: AIDecision(
                                 "BUY" if ai_approved else "SKIP", ai_confidence,
                                 "TEST_APPROVED", ai_source))
                                            if allow and ai_gate_configured else None),
                             risk_gate=((lambda _i, _o, _a: SafetyApproval(
                                 risk_approved, "RISK_APPROVED" if risk_approved else "TEST_RISK_VETO"))
                                        if allow and risk_gate_configured else None))
    return ce, db, clock


def run(ce, key="k1", mode="VALIDATE_ONLY", amount="1"):
    return ce.run(idempotency_key=key, input_mint=MINTS["input_mint"],
                  output_mint=MINTS["output_mint"], in_amount=D(amount), mode=mode)


class StagePlanTest(unittest.TestCase):
    def test_validate_only_reaches_validated_without_simulation_or_signing(self):
        rpc, signer = FakeRpc(), FakeSigner()
        ce, _, _ = make(rpc=rpc, signer=signer)
        a = run(ce)
        self.assertEqual(a.state, "VALIDATED")
        self.assertEqual(signer.calls, 0)

    def test_simulate_only_records_simulated_and_never_signs(self):
        signer = FakeSigner()
        ce, _, _ = make(signer=signer)
        self.assertEqual(run(ce, mode="SIMULATE_ONLY").state, "SIMULATED")
        self.assertEqual(signer.calls, 0)

    def test_broadcast_refused_by_default(self):
        signer = FakeSigner()
        ce, _, _ = make(signer=signer)
        a = run(ce, mode="BROADCAST")
        self.assertEqual((a.state, a.reason), ("REJECTED", "BROADCAST_DISABLED"))
        self.assertEqual(signer.calls, 0)

    def test_unknown_mode_rejected(self):
        ce, _, _ = make()
        with self.assertRaises(ValueError):
            run(ce, mode="MAINNET")


class QuoteValidationTest(unittest.TestCase):
    def test_provider_not_allowed(self):
        ce, _, _ = make(quotes=FakeQuotes(provider="unknown-router"))
        self.assertIn("ROUTE_PROVIDER_NOT_ALLOWED", run(ce).reason)

    def test_stale_quote(self):
        q = FakeQuotes(ttl=30)
        clock = clock_at(0)
        ce, _, _ = make(quotes=q, clock=clock)
        q.now = START - timedelta(seconds=60)  # quote issued in the past, already expired
        self.assertIn("QUOTE_STALE", run(ce).reason)

    def test_price_impact_boundary(self):
        ce, _, _ = make(quotes=FakeQuotes(impact="1"))
        self.assertEqual(run(ce).state, "VALIDATED")
        ce2, _, _ = make(quotes=FakeQuotes(impact="1.01"))
        self.assertIn("PRICE_IMPACT_TOO_HIGH", run(ce2).reason)

    def test_amount_mismatch(self):
        ce, _, _ = make(quotes=FakeQuotes(in_amount_override=D("2")))
        self.assertIn("AMOUNT_MISMATCH", run(ce).reason)

    def test_quote_outage_rejected_not_crash(self):
        ce, _, _ = make(quotes=FakeQuotes(fail=True))
        self.assertEqual(run(ce).reason, "QUOTE_UNAVAILABLE")

    def test_zero_out_amount_is_domain_error_at_quote_construction(self):
        with self.assertRaises(DomainError):
            FakeQuotes(out="0").quote(MINTS["input_mint"], MINTS["output_mint"], D("1"))


class PlanInspectionTest(unittest.TestCase):
    def test_unknown_program_rejected(self):
        ce, _, _ = make(builder=FakeBuilder(programs=("EvilProgram1111111111111111111111111111",)))
        self.assertIn("UNKNOWN_PROGRAM", run(ce).reason)

    def test_unknown_destination_rejected(self):
        ce, _, _ = make(builder=FakeBuilder(destination="Attacker11111111111111111111111111111111"))
        self.assertIn("UNKNOWN_DESTINATION", run(ce).reason)

    def test_foreign_source_rejected(self):
        ce, _, _ = make(builder=FakeBuilder(source="OtherWallet111111111111111111111111111111"))
        self.assertIn("FOREIGN_SOURCE", run(ce).reason)

    def test_transfer_total_must_equal_quote_input(self):
        ce, _, _ = make(builder=FakeBuilder(spend=D("1.5")))
        self.assertIn("TRANSFER_TOTAL_MISMATCH", run(ce).reason)

    def test_fee_payer_must_be_owner(self):
        ce, _, _ = make(builder=FakeBuilder(fee_payer="Someone11111111111111111111111111111111"))
        self.assertIn("FEE_PAYER_NOT_OWNER", run(ce).reason)


class SimulationTest(unittest.TestCase):
    def test_insufficient_funds_maps_to_clear_reason(self):
        ce, _, _ = make(rpc=FakeRpc(simulate_error="INSUFFICIENT_FUNDS"))
        self.assertEqual(run(ce).reason, "INSUFFICIENT_BALANCE")

    def test_other_simulation_failure(self):
        ce, _, _ = make(rpc=FakeRpc(simulate_error="PROGRAM_ERROR"))
        self.assertEqual(run(ce).reason, "SIMULATION_FAILED")

    def test_rpc_outage_during_simulation(self):
        ce, _, _ = make(rpc=FakeRpc(sim_down=True))
        self.assertEqual(run(ce).reason, "RPC_UNAVAILABLE")


class IdempotencyAndRestartTest(unittest.TestCase):
    def test_same_key_returns_original_attempt_without_new_work(self):
        rpc = FakeRpc()
        ce, db, _ = make(rpc=rpc)
        first = run(ce, key="same", mode="SIMULATE_ONLY")
        second = run(ce, key="same", mode="BROADCAST", amount="999")
        self.assertEqual(first.id, second.id)
        self.assertEqual(second.state, "SIMULATED")
        self.assertEqual(db.query_one("SELECT COUNT(*) AS n FROM chain_attempts")["n"], 1)

    def test_attempt_survives_new_controller_instance(self):
        ce, db, clock = make()
        first = run(ce, key="persist")
        ce2, _, _ = make(db=db, clock=clock)
        self.assertEqual(run(ce2, key="persist").id, first.id)


class BroadcastPathTest(unittest.TestCase):
    """Broadcast can only be exercised with an injected fake signer, in tests."""

    def test_confirmed_path(self):
        rpc = FakeRpc(status_seq=("PROCESSED", "CONFIRMED"))
        ce, _, _ = make(rpc=rpc, allow=True)
        a = run(ce, mode="BROADCAST")
        self.assertEqual(a.state, "SUBMITTED")  # first poll: processed, still pending
        confirmed = ce.reconcile(a.id)
        self.assertEqual(confirmed.state, "CONFIRMED")
        self.assertIsNone(confirmed.reason)
        self.assertEqual(len(rpc.sent), 1)

    def test_on_chain_failure(self):
        rpc = FakeRpc(status_seq=("FAILED",))
        ce, _, _ = make(rpc=rpc, allow=True)
        a = run(ce, mode="BROADCAST")
        self.assertEqual(a.state, "FAILED")
        self.assertEqual(a.reason, "ON_CHAIN_FAILURE")

    def test_send_timeout_is_unknown_and_never_resubmitted(self):
        rpc = FakeRpc(send_fails=True)
        ce, _, _ = make(rpc=rpc, allow=True)
        a = run(ce, mode="BROADCAST")
        self.assertEqual((a.state, a.reason), ("UNKNOWN", "SEND_OUTCOME_UNKNOWN"))
        again = run(ce, mode="BROADCAST")
        self.assertEqual(again.id, a.id)
        self.assertEqual(len(rpc.sent), 0)

    def test_unexpected_send_exception_is_unknown_and_never_resubmitted(self):
        class UnexpectedRpc(FakeRpc):
            def send(self, signed):
                raise RuntimeError("unexpected transport failure")

        rpc = UnexpectedRpc()
        ce, _, _ = make(rpc=rpc, allow=True)
        first = run(ce, mode="BROADCAST")
        second = run(ce, mode="BROADCAST")
        self.assertEqual((first.state, first.reason), ("UNKNOWN", "SEND_OUTCOME_UNKNOWN"))
        self.assertEqual(second.id, first.id)
        self.assertEqual(rpc.sent, [])

    def test_idempotency_intent_is_committed_before_rpc_send(self):
        db = Database(":memory:")
        db.migrate()

        class InspectingRpc(FakeRpc):
            def send(self, signed):
                row = db.query_one(
                    "SELECT state FROM chain_attempts WHERE idempotency_key = ?", ("k1",)
                )
                self.assert_state = row["state"] if row else None
                return super().send(signed)

        rpc = InspectingRpc()
        ce, _, _ = make(rpc=rpc, allow=True, db=db)
        attempt = run(ce, mode="BROADCAST")
        self.assertEqual(rpc.assert_state, "UNKNOWN")
        self.assertEqual(attempt.state, "CONFIRMED")
        db.close()

    def test_dropped_only_after_plan_expiry(self):
        rpc = FakeRpc(status_seq=("NOT_FOUND",))
        clock = clock_at(0)
        ce, _, _ = make(rpc=rpc, allow=True, clock=clock)
        a = run(ce, mode="BROADCAST")
        self.assertEqual(a.state, "UNKNOWN")       # not found yet, plan still valid: no resubmit
        self.assertEqual(ce.reconcile(a.id).state, "UNKNOWN")
        clock.advance(121)
        self.assertEqual(ce.reconcile(a.id).state, "DROPPED")

    def test_signer_disabled_blocks_broadcast_even_when_allowed(self):
        from bangzen_prime.infrastructure.adapters.execution.signing import DisabledSigner
        ce, _, _ = make(allow=True, signer=DisabledSigner())
        a = run(ce, mode="BROADCAST")
        self.assertEqual((a.state, a.reason), ("REJECTED", "SIGNER_DISABLED"))

    def test_broadcast_requires_independent_risk_gate(self):
        rpc, signer = FakeRpc(), FakeSigner()
        ce, _, _ = make(rpc=rpc, signer=signer, allow=True, risk_gate_configured=False)
        attempt = run(ce, mode="BROADCAST")
        self.assertEqual((attempt.state, attempt.reason),
                         ("REJECTED", "RISK_APPROVAL_UNAVAILABLE"))
        self.assertEqual(signer.calls, 0)
        self.assertEqual(rpc.sent, [])

    def test_risk_veto_blocks_even_when_ai_approves(self):
        rpc, signer = FakeRpc(), FakeSigner()
        ce, _, _ = make(rpc=rpc, signer=signer, allow=True,
                        ai_approved=True, risk_approved=False)
        attempt = run(ce, mode="BROADCAST")
        self.assertEqual((attempt.state, attempt.reason),
                         ("REJECTED", "RISK_APPROVAL_DENIED"))
        self.assertEqual(signer.calls, 0)
        self.assertEqual(rpc.sent, [])

    def test_invalid_risk_gate_result_fails_closed(self):
        rpc, signer = FakeRpc(), FakeSigner()
        ce, _, _ = make(rpc=rpc, signer=signer, allow=True)
        ce._risk_gate = lambda _i, _o, _a: True
        attempt = run(ce, mode="BROADCAST")
        self.assertEqual(attempt.reason, "RISK_APPROVAL_DENIED")
        self.assertEqual(signer.calls, 0)
        self.assertEqual(rpc.sent, [])

    def test_risk_gate_exception_fails_closed_before_ai_or_quote(self):
        rpc, signer = FakeRpc(), FakeSigner()
        quotes = FakeQuotes()
        ce, _, _ = make(rpc=rpc, signer=signer, quotes=quotes, allow=True)
        ce._risk_gate = lambda _i, _o, _a: (_ for _ in ()).throw(RuntimeError("risk source down"))
        attempt = run(ce, mode="BROADCAST")
        self.assertEqual(attempt.reason, "RISK_APPROVAL_DENIED")
        self.assertEqual(signer.calls, 0)
        self.assertEqual(rpc.sent, [])

    def test_broadcast_requires_ai_approval_gate(self):
        rpc, signer = FakeRpc(), FakeSigner()
        ce, _, _ = make(rpc=rpc, signer=signer, allow=True, ai_gate_configured=False)
        attempt = run(ce, mode="BROADCAST")
        self.assertEqual((attempt.state, attempt.reason),
                         ("REJECTED", "AI_APPROVAL_UNAVAILABLE"))
        self.assertEqual(signer.calls, 0)
        self.assertEqual(rpc.sent, [])

    def test_ai_veto_blocks_before_quote_and_signing(self):
        rpc, signer = FakeRpc(), FakeSigner()
        quotes = FakeQuotes()
        ce, _, _ = make(quotes=quotes, rpc=rpc, signer=signer, allow=True,
                        ai_approved=False)
        attempt = run(ce, mode="BROADCAST")
        self.assertEqual(attempt.reason, "AI_APPROVAL_DENIED")
        self.assertEqual(signer.calls, 0)
        self.assertEqual(rpc.sent, [])

    def test_fallback_ai_decision_cannot_approve_broadcast(self):
        rpc, signer = FakeRpc(), FakeSigner()
        ce, _, _ = make(rpc=rpc, signer=signer, allow=True, ai_source="fallback")
        attempt = run(ce, mode="BROADCAST")
        self.assertEqual(attempt.reason, "AI_APPROVAL_DENIED")
        self.assertEqual(signer.calls, 0)
        self.assertEqual(rpc.sent, [])

    def test_low_confidence_ai_buy_cannot_approve_broadcast(self):
        rpc, signer = FakeRpc(), FakeSigner()
        ce, _, _ = make(rpc=rpc, signer=signer, allow=True,
                        ai_confidence=D("0.59"))
        attempt = run(ce, mode="BROADCAST")
        self.assertEqual(attempt.reason, "AI_APPROVAL_DENIED")
        self.assertEqual(signer.calls, 0)
        self.assertEqual(rpc.sent, [])


class BalanceReconciliationTest(unittest.TestCase):
    def test_within_tolerance(self):
        self.assertTrue(balance_delta_matches(before=D(0), after=D("50.4"), expected_increase=D(50),
                                              tolerance_pct=D("1")))

    def test_outside_tolerance(self):
        self.assertFalse(balance_delta_matches(before=D(0), after=D("40"), expected_increase=D(50),
                                               tolerance_pct=D("1")))

    def test_non_positive_expectation_rejected(self):
        with self.assertRaises(DomainError):
            balance_delta_matches(before=D(0), after=D(1), expected_increase=D(0), tolerance_pct=D(1))


if __name__ == "__main__":
    unittest.main()
