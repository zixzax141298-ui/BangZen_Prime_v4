"""AI analyst contract tests. The model is an analyst only: it cannot return a trade decision."""

import json
import unittest
from decimal import Decimal

from bangzen_prime.research.ai_brain import (
    ANALYSIS,
    NO_ANALYSIS,
    SYSTEM_PROMPT,
    AIBrain,
    TradeContext,
    build_user_prompt,
    parse_analysis,
)


def context(**overrides):
    values = {
        "mint": "So11111111111111111111111111111111111111112",
        "symbol": "SAFE",
        "liquidity_usd": Decimal(25000),
        "volume_24h_usd": Decimal(50000),
        "top10_holder_share_pct": Decimal("12.5"),
        "holder_count": 500,
        "heuristic_score": Decimal(75),
        "safety_risk_score": Decimal(10),
        "rugged": False,
    }
    values.update(overrides)
    return TradeContext(**values)


def analysis_payload(**overrides):
    body = {
        "risk_level": "LOW",
        "summary": "Holder distribution and liquidity look consistent with the data supplied.",
        "flags": ["INSUFFICIENT_EVIDENCE"],
        "confidence": 0.7,
    }
    body.update(overrides)
    return json.dumps(body)


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


class AIAnalystContractTests(unittest.TestCase):
    def test_prompt_includes_phase_and_macro_sentiment_as_separate_context(self):
        prompt = build_user_prompt(
            context(
                token_phase="LAUNCH",
                market_sentiment_pct=Decimal("67.5"),
                market_sentiment_age_seconds=90,
                market_sentiment_trend="up",
            )
        )
        self.assertIn('"token_phase": "LAUNCH"', prompt)
        self.assertIn('"market_sentiment_pct": "67.5"', prompt)
        self.assertIn('"market_sentiment_age_seconds": 90', prompt)

    def test_system_prompt_forbids_trading_outputs(self):
        for word in ("never recommend buying", "selling", "stop losses", "position sizes"):
            self.assertIn(word, SYSTEM_PROMPT)
        self.assertNotIn("decision (BUY or SKIP)", SYSTEM_PROMPT)
        self.assertIn("Do not include any key named decision", SYSTEM_PROMPT)

    def test_valid_analysis_is_accepted_and_carries_no_trade_meaning(self):
        result = parse_analysis(analysis_payload())
        self.assertEqual(result.decision, ANALYSIS)
        self.assertEqual(result.risk_level, "LOW")
        self.assertEqual(result.flags, ("INSUFFICIENT_EVIDENCE",))
        self.assertNotIn(result.decision, ("BUY", "SELL", "HOLD", "SKIP"))

    def test_buy_decision_is_rejected(self):
        payload = json.dumps(
            {"decision": "BUY", "confidence": 0.9, "reason": "looks good"}
        )
        self.assertEqual(parse_analysis(payload).decision, NO_ANALYSIS)

    def test_trade_like_extra_keys_are_rejected(self):
        for key in ("action", "buy", "sell", "hold", "size", "stop_loss", "take_profit"):
            with self.subTest(key=key):
                payload = json.loads(analysis_payload())
                payload[key] = "x"
                self.assertEqual(parse_analysis(json.dumps(payload)).decision, NO_ANALYSIS)

    def test_extra_prose_is_rejected_instead_of_extracting_json(self):
        self.assertEqual(
            parse_analysis("Sure! " + analysis_payload()).decision, NO_ANALYSIS
        )

    def test_duplicate_keys_are_rejected(self):
        text = '{"risk_level":"LOW","risk_level":"HIGH","summary":"x","flags":[],"confidence":0.5}'
        self.assertEqual(parse_analysis(text).decision, NO_ANALYSIS)

    def test_unknown_risk_level_and_flags_are_rejected(self):
        self.assertEqual(parse_analysis(analysis_payload(risk_level="BUY")).decision, NO_ANALYSIS)
        self.assertEqual(parse_analysis(analysis_payload(flags=["MADE_UP"])).decision, NO_ANALYSIS)
        self.assertEqual(
            parse_analysis(analysis_payload(flags=["OTHER"] * 7)).decision, NO_ANALYSIS
        )

    def test_non_finite_and_boolean_confidence_are_rejected(self):
        self.assertEqual(parse_analysis(analysis_payload(confidence=True)).decision, NO_ANALYSIS)
        self.assertEqual(parse_analysis(analysis_payload(confidence=1.5)).decision, NO_ANALYSIS)
        self.assertEqual(
            parse_analysis('{"risk_level":"LOW","summary":"x","flags":[],"confidence":NaN}').decision,
            NO_ANALYSIS,
        )

    def test_empty_or_oversized_summary_is_rejected(self):
        self.assertEqual(parse_analysis(analysis_payload(summary="   ")).decision, NO_ANALYSIS)
        self.assertEqual(parse_analysis(analysis_payload(summary="x" * 201)).decision, NO_ANALYSIS)

    def test_invalid_market_sentiment_fails_before_provider_call(self):
        provider = Provider(response=analysis_payload())
        result = AIBrain(provider).analyze(context(market_sentiment_pct=Decimal("101")))
        self.assertEqual(result.reason, "INVALID_MARKET_SENTIMENT")
        self.assertEqual(provider.calls, 0)

    def test_missing_holder_data_fails_closed_without_calling_provider(self):
        provider = Provider(response=analysis_payload())
        result = AIBrain(provider).analyze(context(top10_holder_share_pct=None, holder_count=None))
        self.assertEqual(result.decision, NO_ANALYSIS)
        self.assertEqual(result.reason, "HOLDER_DATA_UNAVAILABLE")
        self.assertEqual(provider.calls, 0)

    def test_invalid_mint_is_rejected_before_provider_call(self):
        provider = Provider(response=analysis_payload())
        result = AIBrain(provider).analyze(context(mint="not-a-mint"))
        self.assertEqual(result.reason, "INVALID_MINT")
        self.assertEqual(provider.calls, 0)

    def test_provider_unexpected_exception_fails_closed(self):
        provider = Provider(error=RuntimeError("boom"))
        result = AIBrain(provider).analyze(context())
        self.assertEqual((result.decision, result.reason), (NO_ANALYSIS, "AI_UNAVAILABLE"))

    def test_identical_evidence_reuses_recent_analysis(self):
        provider = Provider(response=analysis_payload())
        now = [1000.0]
        brain = AIBrain(provider, cache_ttl_seconds=30, clock=lambda: now[0])
        brain.analyze(context())
        brain.analyze(context())
        self.assertEqual(provider.calls, 1)
        now[0] += 31
        brain.analyze(context())
        self.assertEqual(provider.calls, 2)


if __name__ == "__main__":
    unittest.main()
