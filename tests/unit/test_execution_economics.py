import unittest
from decimal import Decimal

from bangzen_prime.domain.execution_economics import (
    ExecutionCostBreakdown,
    calculate_net_execution_economics,
)
from bangzen_prime.errors import DomainError

D = Decimal


class ExecutionCostBreakdownTests(unittest.TestCase):
    def test_sums_every_cost_category(self):
        costs = ExecutionCostBreakdown(
            entry_fee_quote="0.1", exit_fee_quote="0.2",
            entry_slippage_quote="0.3", exit_slippage_quote="0.4",
            entry_price_impact_quote="0.5", exit_price_impact_quote="0.6",
            priority_fee_quote="0.01", jito_tip_quote="0.02",
            rent_reserve_quote="0.03", failed_exit_reserve_quote="0.04",
            other_cost_quote="0.05",
        )
        self.assertEqual(costs.total_quote, D("2.25"))

    def test_negative_non_finite_and_float_costs_are_rejected(self):
        for value in (-1, "NaN", "Infinity", 0.1, True):
            with self.subTest(value=value), self.assertRaises(DomainError):
                ExecutionCostBreakdown(entry_fee_quote=value)

    def test_string_and_integer_costs_normalize_to_decimal(self):
        costs = ExecutionCostBreakdown(entry_fee_quote="0.25", exit_fee_quote=1)
        self.assertEqual(costs.entry_fee_quote, D("0.25"))
        self.assertEqual(costs.exit_fee_quote, D(1))


class NetExecutionEconomicsTests(unittest.TestCase):
    def test_profitable_trade_after_all_round_trip_costs(self):
        costs = ExecutionCostBreakdown(
            entry_fee_quote="0.10", exit_fee_quote="0.12",
            entry_slippage_quote="0.05", exit_slippage_quote="0.08",
            entry_price_impact_quote="0.02", exit_price_impact_quote="0.03",
            priority_fee_quote="0.01", jito_tip_quote="0.02",
            rent_reserve_quote="0.01", failed_exit_reserve_quote="0.04",
        )
        result = calculate_net_execution_economics(
            entry_notional_quote="100", expected_exit_gross_quote="102", costs=costs,
        )
        self.assertEqual(result.total_cost_quote, D("0.48"))
        self.assertEqual(result.gross_pnl_quote, D("2"))
        self.assertEqual(result.net_pnl_quote, D("1.52"))
        self.assertEqual(result.break_even_exit_gross_quote, D("100.48"))
        self.assertEqual(result.net_return_pct, D("1.52"))
        self.assertTrue(result.net_profitable)

    def test_gross_winner_can_be_net_loser_after_costs(self):
        result = calculate_net_execution_economics(
            entry_notional_quote="100", expected_exit_gross_quote="100.5",
            costs=ExecutionCostBreakdown(
                entry_fee_quote="0.2", exit_fee_quote="0.2",
                entry_slippage_quote="0.1", exit_slippage_quote="0.1",
            ),
        )
        self.assertEqual(result.gross_pnl_quote, D("0.5"))
        self.assertEqual(result.net_pnl_quote, D("-0.1"))
        self.assertFalse(result.net_profitable)

    def test_break_even_exit_includes_every_cost(self):
        costs = ExecutionCostBreakdown(
            entry_fee_quote="0.1", exit_fee_quote="0.1",
            priority_fee_quote="0.01", jito_tip_quote="0.02",
        )
        result = calculate_net_execution_economics(
            entry_notional_quote="10", expected_exit_gross_quote="10.23", costs=costs,
        )
        self.assertEqual(result.break_even_exit_gross_quote, D("10.23"))
        self.assertEqual(result.net_pnl_quote, D("0.00"))
        self.assertFalse(result.net_profitable)

    def test_loss_and_cost_percentages_are_quote_normalized(self):
        result = calculate_net_execution_economics(
            entry_notional_quote="200", expected_exit_gross_quote="190",
            costs=ExecutionCostBreakdown(priority_fee_quote="2", jito_tip_quote="1"),
        )
        self.assertEqual(result.net_pnl_quote, D("-13"))
        self.assertEqual(result.net_return_pct, D("-6.5"))
        self.assertEqual(result.total_cost_pct, D("1.5"))

    def test_rejects_invalid_notionals_and_cost_object(self):
        for value in (0, -1, "NaN", "Infinity", 1.2, True):
            with self.subTest(value=value), self.assertRaises(DomainError):
                calculate_net_execution_economics(
                    entry_notional_quote=value, expected_exit_gross_quote="10",
                    costs=ExecutionCostBreakdown(),
                )
        with self.assertRaises(DomainError):
            calculate_net_execution_economics(
                entry_notional_quote="10", expected_exit_gross_quote="10",
                costs={},  # type: ignore[arg-type]
            )


if __name__ == "__main__":
    unittest.main()
