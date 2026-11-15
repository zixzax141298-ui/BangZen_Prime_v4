import unittest
from decimal import Decimal as D

from bangzen_prime.core.errors import DomainError
from bangzen_prime.research.cost_model import (
    AVAILABLE,
    UNAVAILABLE,
    CostInputs,
    estimate_costs,
)


def _complete(**overrides) -> CostInputs:
    values = dict(
        notional=D(100),
        fee_rate_per_side=D("0.001"),
        base_slippage_rate=D("0.001"),
        liquidity_quote=D(10000),
        impact_coefficient=D("0.5"),
        priority_fee_quote=D("0.01"),
        tx_failure_rate=D("0.5"),
    )
    values.update(overrides)
    return CostInputs(**values)


class CostModelTest(unittest.TestCase):
    def test_unmeasured_inputs_are_unavailable_and_named_never_zero(self):
        estimate = estimate_costs(_complete(priority_fee_quote=None, tx_failure_rate=None))
        self.assertEqual(estimate.status, UNAVAILABLE)
        self.assertIn("priority_fee_quote", estimate.missing)
        self.assertIn("tx_failure_rate", estimate.missing)
        self.assertIsNone(estimate.expected_fixed_cost_per_trade)
        self.assertIsNone(estimate.slippage_rate_per_side)

    def test_unavailable_estimate_refuses_to_build_a_backtest_config(self):
        estimate = estimate_costs(_complete(liquidity_quote=None))
        with self.assertRaises(DomainError) as ctx:
            estimate.to_backtest_config(D(1000), D(100), 10)
        self.assertIn("liquidity_quote(>0)", str(ctx.exception))

    def test_zero_liquidity_is_unavailable_not_infinite_depth(self):
        estimate = estimate_costs(_complete(liquidity_quote=D(0)))
        self.assertEqual(estimate.status, UNAVAILABLE)
        self.assertIn("liquidity_quote(>0)", estimate.missing)

    def test_available_estimate_uses_linear_impact_and_geometric_retries(self):
        estimate = estimate_costs(_complete())
        self.assertEqual(estimate.status, AVAILABLE)
        # 0.001 + 0.5 * (100 / 10000) = 0.006
        self.assertEqual(estimate.slippage_rate_per_side, D("0.006"))
        # 2 transactions * 0.01 priority / (1 - 0.5) = 0.04
        self.assertEqual(estimate.expected_fixed_cost_per_trade, D("0.04"))
        self.assertTrue(estimate.notes)

    def test_available_estimate_builds_backtest_config(self):
        config = estimate_costs(_complete()).to_backtest_config(D(1000), D(100), 30)
        self.assertEqual(config.fee_rate_per_side, D("0.001"))
        self.assertEqual(config.slippage_rate_per_side, D("0.006"))
        self.assertEqual(config.fixed_cost_per_trade, D("0.04"))
        self.assertEqual(config.max_holding_candles, 30)

    def test_failure_rate_of_one_or_more_is_invalid_not_unavailable(self):
        with self.assertRaises(DomainError):
            _complete(tx_failure_rate=D(1))

    def test_negative_or_non_decimal_inputs_are_rejected(self):
        with self.assertRaises(DomainError):
            _complete(priority_fee_quote=D("-0.01"))
        with self.assertRaises(DomainError):
            _complete(fee_rate_per_side=0.001)  # float is not allowed
        with self.assertRaises(DomainError):
            CostInputs(notional=D(0))

    def test_slippage_at_or_above_one_is_rejected(self):
        with self.assertRaises(DomainError):
            estimate_costs(_complete(base_slippage_rate=D("0.9"), impact_coefficient=D(100)))


if __name__ == "__main__":
    unittest.main()
