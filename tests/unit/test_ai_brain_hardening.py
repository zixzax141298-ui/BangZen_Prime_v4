import json
import unittest
from decimal import Decimal

from bangzen_prime.application.ai_brain import (
    AIBrain, TradeContext, ai_decision_gate, ai_gate, build_user_prompt, parse_decision,
)


def context(**overrides):
    values = {
        "mint": "So11111111111111111111111111111111111111112",
        "symbol": "SAFE",
        "liquidity_usd": Decimal("25000"),
        "volume_24h_usd": Decimal("50000"),
        "top10_holder_share_pct": Decimal("12.5"),
        "holder_count": 500,
        "heuristic_score": Decimal("75"),
        "safety_risk_score": Decimal("10"),
        "rugged": False,
    }
    values.update(overrides)
    return TradeContext(**values)


class Provider:
    name = "test"

    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = 0

    def complete(self, system, user):
        self.calls += 1
        if self.error:
            raise self.error
        return self.response


class AIDecisionHardeningTests(unittest.TestCase):
    def test_prompt_includes_phase_and_macro_sentiment_as_separate_context(self):
        prompt = build_user_prompt(context(
            token_phase="LAUNCH", market_sentiment_pct=Decimal("67.5"),
            market_sentiment_age_seconds=90, market_sentiment_trend="up",
        ))
        self.assertIn('"token_phase": "LAUNCH"', prompt)
        self.assertIn('"market_sentiment_pct": "67.5"', prompt)
        self.assertIn('"market_sentiment_age_seconds": 90', prompt)

    def test_invalid_market_sentiment_fails_before_provider_call(self):
        provider = Provider('{"decision":"BUY","confidence":1,"reason":"x"}')
        result = AIBrain(provider, threshold=Decimal("0.6")).decide(
            context(market_sentiment_pct=Decimal("101"))
        )
        self.assertEqual(result.reason, "INVALID_MARKET_SENTIMENT")
        self.assertEqual(provider.calls, 0)

    def test_identical_evidence_reuses_recent_model_decision(self):
        response = json.dumps({"decision": "SKIP", "confidence": 0.8, "reason": "No edge"})
        provider = Provider(response)
        now = [100.0]
        brain = AIBrain(provider, threshold=Decimal("0.6"),
                         cache_ttl_seconds=30, clock=lambda: now[0])
        first = brain.decide(context())
        second = brain.decide(context())
        self.assertEqual(first, second)
        self.assertEqual(provider.calls, 1)
        now[0] = 131.0
        brain.decide(context())
        self.assertEqual(provider.calls, 2)

    def test_valid_buy_is_accepted(self):
        response = json.dumps({"decision": "BUY", "confidence": 0.91, "reason": "Evidence supports setup"})
        brain = AIBrain(Provider(response), threshold=Decimal("0.8"))
        self.assertEqual(brain.decide(context()).decision, "BUY")

    def test_extra_prose_is_rejected_instead_of_extracting_json(self):
        response = 'BUY NOW ' + json.dumps({"decision": "BUY", "confidence": 0.99, "reason": "looks good"})
        self.assertEqual(parse_decision(response, Decimal("0.6")).decision, "SKIP")

    def test_extra_keys_are_rejected(self):
        response = json.dumps({"decision": "BUY", "confidence": 0.99, "reason": "ok", "wallet_action": "execute"})
        self.assertEqual(parse_decision(response, Decimal("0.6")).decision, "SKIP")

    def test_duplicate_keys_are_rejected(self):
        response = '{"decision":"SKIP","decision":"BUY","confidence":1,"reason":"x"}'
        self.assertEqual(parse_decision(response, Decimal("0.6")).decision, "SKIP")

    def test_non_finite_confidence_is_rejected(self):
        self.assertEqual(parse_decision('{"decision":"BUY","confidence":NaN,"reason":"x"}',
                                        Decimal("0.6")).decision, "SKIP")

    def test_boolean_confidence_is_rejected(self):
        self.assertEqual(parse_decision('{"decision":"BUY","confidence":true,"reason":"x"}',
                                        Decimal("0.6")).decision, "SKIP")

    def test_empty_reason_is_rejected(self):
        self.assertEqual(parse_decision('{"decision":"BUY","confidence":1,"reason":"  "}',
                                        Decimal("0.6")).decision, "SKIP")

    def test_low_confidence_buy_becomes_skip(self):
        result = parse_decision('{"decision":"BUY","confidence":0.4,"reason":"maybe"}',
                                Decimal("0.6"))
        self.assertEqual(result.decision, "SKIP")
        self.assertEqual(result.reason, "CONFIDENCE_BELOW_THRESHOLD")

    def test_missing_holder_data_fails_closed_without_calling_provider(self):
        provider = Provider(json.dumps({"decision": "BUY", "confidence": 1, "reason": "guess"}))
        result = AIBrain(provider, threshold=Decimal("0.6")).decide(
            context(top10_holder_share_pct=None, holder_count=None)
        )
        self.assertEqual(result.decision, "SKIP")
        self.assertEqual(result.reason, "HOLDER_DATA_UNAVAILABLE")
        self.assertEqual(provider.calls, 0)  # No model call is made for incomplete evidence.

    def test_invalid_mint_is_rejected_before_provider_call(self):
        provider = Provider(json.dumps({"decision": "BUY", "confidence": 1, "reason": "guess"}))
        result = AIBrain(provider, threshold=Decimal("0.6")).decide(context(mint="not-a-mint"))
        self.assertEqual(result.decision, "SKIP")
        self.assertEqual(result.reason, "INVALID_MINT")
        self.assertEqual(provider.calls, 0)

    def test_provider_unexpected_exception_fails_closed(self):
        result = AIBrain(Provider(error=RuntimeError("provider failure")),
                         threshold=Decimal("0.6")).decide(context())
        self.assertEqual(result.decision, "SKIP")
        self.assertEqual(result.reason, "AI_UNAVAILABLE")

    def test_typed_ai_decision_gate_returns_model_decision(self):
        brain = AIBrain(
            Provider(json.dumps({"decision": "BUY", "confidence": 0.95, "reason": "supported"})),
            threshold=Decimal("0.6"),
        )
        gate = ai_decision_gate(brain, lambda _i, _o, _a: context())
        decision = gate("input", "output", Decimal("1"))
        self.assertEqual((decision.decision, decision.source), ("BUY", "model"))

    def test_typed_ai_decision_gate_fails_closed_on_context_error(self):
        brain = AIBrain(Provider(""), threshold=Decimal("0.6"))
        gate = ai_decision_gate(
            brain, lambda _i, _o, _a: (_ for _ in ()).throw(RuntimeError("no context"))
        )
        decision = gate("input", "output", Decimal("1"))
        self.assertEqual((decision.decision, decision.source, decision.reason),
                         ("SKIP", "fallback", "AI_CONTEXT_UNAVAILABLE"))

    def test_ai_gate_context_error_fails_closed(self):
        brain = AIBrain(Provider(json.dumps({"decision": "BUY", "confidence": 1, "reason": "ok"})),
                        threshold=Decimal("0.6"))
        allowed, reason = ai_gate(brain, lambda _: (_ for _ in ()).throw(RuntimeError()))(object())
        self.assertFalse(allowed)
        self.assertEqual(reason, "AI_CONTEXT_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
