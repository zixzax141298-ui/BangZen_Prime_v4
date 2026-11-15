import math
import unittest
from unittest.mock import patch

from bangzen_prime.application.strategy_dispatcher import StrategyDispatcher


class StrategyDispatcherValidationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.dispatcher = StrategyDispatcher()

    async def test_missing_age_is_watch(self):
        result = await self.dispatcher.route_and_evaluate({})
        self.assertEqual(result["status"], "WATCH")
        self.assertIn("age_minutes", result["missing_fields"])

    async def test_boolean_age_is_not_numeric(self):
        result = await self.dispatcher.route_and_evaluate(
            {"age_minutes": True}
        )
        self.assertEqual(result["status"], "WATCH")
        self.assertIn("age_minutes", result["missing_fields"])

    async def test_nan_age_is_rejected(self):
        result = await self.dispatcher.route_and_evaluate(
            {"age_minutes": math.nan}
        )
        self.assertEqual(result["status"], "WATCH")

    async def test_negative_age_is_rejected(self):
        result = await self.dispatcher.route_and_evaluate(
            {"age_minutes": -1}
        )
        self.assertEqual(result["status"], "WATCH")

    async def test_missing_market_cap_does_not_route_fresh_token(self):
        result = await self.dispatcher.route_and_evaluate(
            {"age_minutes": 2}
        )
        self.assertEqual(result["status"], "WATCH")
        self.assertIn("mcap", result["missing_fields"])

    async def test_missing_volume_does_not_route_early_token(self):
        result = await self.dispatcher.route_and_evaluate(
            {"age_minutes": 10}
        )
        self.assertEqual(result["status"], "WATCH")
        self.assertIn("vol_1h", result["missing_fields"])

    async def test_missing_change_metrics_does_not_route_mid_age_token(self):
        result = await self.dispatcher.route_and_evaluate(
            {"age_minutes": 60}
        )
        self.assertEqual(result["status"], "WATCH")
        self.assertIn("change_1h", result["missing_fields"])
        self.assertIn("change_5m", result["missing_fields"])

    async def test_missing_narrative_flag_is_not_assumed_false(self):
        result = await self.dispatcher.route_and_evaluate(
            {
                "age_minutes": 60,
                "change_1h": 5,
                "change_5m": 0,
            }
        )
        self.assertEqual(result["status"], "WATCH")
        self.assertIn("has_narrative", result["missing_fields"])

    async def test_missing_graduation_flag_is_not_assumed_false(self):
        result = await self.dispatcher.route_and_evaluate(
            {
                "age_minutes": 300,
                "smart_money": 0,
                "change_1h": 0,
            }
        )
        self.assertEqual(result["status"], "WATCH")
        self.assertIn("is_graduating", result["missing_fields"])

    async def test_missing_smart_money_is_not_assumed_zero(self):
        result = await self.dispatcher.route_and_evaluate(
            {
                "age_minutes": 300,
                "is_graduating": False,
                "change_1h": 0,
            }
        )
        self.assertEqual(result["status"], "WATCH")
        self.assertIn("smart_money", result["missing_fields"])

    async def test_complete_fresh_token_routes_to_sniper_degen(self):
        with patch(
            "bangzen_prime.application.strategy_dispatcher.STRATEGY_REGISTRY",
            {},
        ):
            result = await self.dispatcher.route_and_evaluate(
                {"age_minutes": 2, "mcap": 5_000}
            )
        self.assertEqual(result["status"], "WATCH")
        self.assertEqual(result["reason"], "STRATEGY_NOT_AVAILABLE")
        self.assertEqual(result["strategy"], "sniper_degen")

    async def test_unknown_strategy_error_does_not_leak_exception(self):
        class BrokenStrategy:
            def __init__(self, config):
                raise RuntimeError("secret internal detail")

        with patch(
            "bangzen_prime.application.strategy_dispatcher.STRATEGY_REGISTRY",
            {"sniper_degen": BrokenStrategy},
        ):
            result = await self.dispatcher.route_and_evaluate(
                {"age_minutes": 2, "mcap": 5_000}
            )

        self.assertEqual(result["status"], "WATCH")
        self.assertEqual(result["reason"], "STRATEGY_EVALUATION_ERROR")
        self.assertNotIn("secret internal detail", str(result))


    async def test_exception_message_is_not_written_to_logs(self):
        class BrokenStrategy:
            def __init__(self, config):
                raise RuntimeError("secret internal detail")

        with patch(
            "bangzen_prime.application.strategy_dispatcher.STRATEGY_REGISTRY",
            {"sniper_degen": BrokenStrategy},
        ):
            with self.assertLogs(
                "BANGZEN.Dispatcher", level="ERROR"
            ) as captured:
                result = await self.dispatcher.route_and_evaluate(
                    {"age_minutes": 2, "mcap": 5_000}
                )

        self.assertEqual(result["status"], "WATCH")
        self.assertNotIn(
            "secret internal detail",
            "\\n".join(captured.output),
        )
        self.assertIn("RuntimeError", captured.output[0])


if __name__ == "__main__":
    unittest.main()
