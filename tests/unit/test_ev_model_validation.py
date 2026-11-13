import unittest
from decimal import Decimal

from bangzen_prime.domain.ev_model import calculate_ev_model, validate_trade_plan
from bangzen_prime.errors import DomainError


D = Decimal


class ExpectedValueValidationTest(unittest.TestCase):
    def test_rejects_non_finite_inputs(self):
        with self.assertRaises(DomainError):
            calculate_ev_model(D("NaN"), D("1"))
        with self.assertRaises(DomainError):
            calculate_ev_model(D("10"), D("Infinity"))

    def test_rejects_negative_costs_and_invalid_exit_split(self):
        with self.assertRaises(DomainError):
            calculate_ev_model(D("10"), D("-0.1"))
        with self.assertRaises(DomainError):
            calculate_ev_model(D("10"), D("1"), tp1_sell_pct=D("100.1"))

    def test_rejects_non_increasing_targets_and_invalid_buffer(self):
        with self.assertRaises(DomainError):
            calculate_ev_model(D("10"), D("1"), tp1_pct=D("50"), tp2_pct=D("50"))
        with self.assertRaises(DomainError):
            calculate_ev_model(D("10"), D("1"), tp1_pct=D("50"), breakeven_buffer=D("51"))

    def test_valid_ev_outputs_are_finite(self):
        result = calculate_ev_model(D("15"), D("1.2"))
        self.assertEqual(set(result), {"p1_random", "q_random", "p1_breakeven", "ev_random_net"})
        self.assertTrue(all(value.is_finite() for value in result.values()))

    def test_trade_plan_rejects_nan_and_negative_costs(self):
        with self.assertRaises(DomainError):
            validate_trade_plan(D("10"), D("9"), D("12"), D("NaN"))
        with self.assertRaises(DomainError):
            validate_trade_plan(D("10"), D("9"), D("12"), D("-1"))

    def test_trade_plan_rejects_non_positive_net_profit(self):
        result = validate_trade_plan(D("10"), D("9"), D("10.5"), D("5.5"))
        self.assertFalse(result.is_valid)
        self.assertEqual(result.reason, "NON_POSITIVE_NET_PROFIT")

    def test_trade_plan_rejects_invalid_level_geometry(self):
        result = validate_trade_plan(D("10"), D("10"), D("12"), D("0.1"))
        self.assertFalse(result.is_valid)
        self.assertEqual(result.reason, "INVALID_LEVELS")


if __name__ == "__main__":
    unittest.main()
