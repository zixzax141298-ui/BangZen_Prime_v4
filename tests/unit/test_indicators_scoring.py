import unittest
from decimal import Decimal

from bangzen_prime.application.indicators import ema, mean_abs_change, rsi, sma, zscore
from bangzen_prime.application.scoring import score_token
from bangzen_prime.errors import DomainError

D = Decimal


class IndicatorTest(unittest.TestCase):
    def test_sma(self):
        self.assertEqual(sma([D(1), D(2), D(3), D(4)], 2), D("3.5"))

    def test_sma_needs_enough_values(self):
        with self.assertRaises(DomainError):
            sma([D(1)], 2)
        with self.assertRaises(DomainError):
            sma([D(1)], 0)

    def test_ema_seed_and_recursion(self):
        # seed = (1+2)/2 = 1.5; alpha = 2/3; then 2.5; then 3.5
        self.assertAlmostEqual(ema([D(1), D(2), D(3), D(4)], 2), D("3.5"), places=20)
        self.assertEqual(ema([D(10), D(10), D(10)], 2), D(10))

    def test_rsi_flat_series_is_neutral_50(self):
        self.assertEqual(rsi([D(5)] * 20, 14), D(50))

    def test_rsi_monotonic_bounds(self):
        up = [D(i) for i in range(1, 21)]
        down = [D(100 - i) for i in range(20)]
        self.assertEqual(rsi(up, 14), D(100))
        self.assertEqual(rsi(down, 14), D(0))

    def test_rsi_within_0_100_for_mixed_series(self):
        series = [
            D(x) for x in (10, 11, 9, 12, 8, 13, 7, 14, 6, 15, 5, 16, 4, 17, 3, 18)
        ]
        value = rsi(series, 14)
        self.assertTrue(D(0) <= value <= D(100))

    def test_rsi_needs_period_plus_one(self):
        with self.assertRaises(DomainError):
            rsi([D(1)] * 14, 14)

    def test_mean_abs_change_flat_is_zero(self):
        self.assertEqual(mean_abs_change([D(3)] * 20, 14), D(0))

    def test_mean_abs_change_positive_for_moves(self):
        self.assertEqual(mean_abs_change([D(1), D(2), D(1), D(2)], 3), D(1))

    def test_zscore_zero_variance_returns_zero(self):
        self.assertEqual(zscore([D(4), D(4), D(4)]), D(0))

    def test_zscore_sign_follows_last_value(self):
        self.assertTrue(zscore([D(1), D(2), D(3), D(10)]) > 0)
        self.assertTrue(zscore([D(10), D(2), D(3), D(1)]) < 0)

    def test_zscore_needs_two_values(self):
        with self.assertRaises(DomainError):
            zscore([D(1)])


class ScoringTest(unittest.TestCase):
    def test_score_bounds_and_confidence(self):
        b = score_token(
            liquidity_usd=D("1000000"),
            volume_24h_usd=D("9000000"),
            risk_score=D(0),
            rsi_value=D(55),
        )
        self.assertEqual(b.total, D("100.00"))
        self.assertEqual(b.confidence, D("1.00"))

    def test_zero_everything_low_score(self):
        b = score_token(
            liquidity_usd=D(0), volume_24h_usd=D(0), risk_score=D(100), rsi_value=D(0)
        )
        self.assertEqual(b.total, D("0.00"))

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(DomainError):
            score_token(
                liquidity_usd=D(-1),
                volume_24h_usd=D(0),
                risk_score=D(0),
                rsi_value=D(50),
            )
        with self.assertRaises(DomainError):
            score_token(
                liquidity_usd=D(1),
                volume_24h_usd=D(0),
                risk_score=D(101),
                rsi_value=D(50),
            )
        with self.assertRaises(DomainError):
            score_token(
                liquidity_usd=D(1),
                volume_24h_usd=D(0),
                risk_score=D(0),
                rsi_value=D("NaN"),
            )

    def test_early_phase_weights_liquidity_less_than_mature_phase(self):
        early = score_token(
            liquidity_usd=D(5000),
            volume_24h_usd=D(300000),
            risk_score=D(10),
            rsi_value=D(55),
            phase="LAUNCH",
        )
        mature = score_token(
            liquidity_usd=D(5000),
            volume_24h_usd=D(300000),
            risk_score=D(10),
            rsi_value=D(55),
            phase="MATURE",
        )
        self.assertGreater(early.total, mature.total)

    def test_unknown_phase_is_rejected_as_bad_context(self):
        with self.assertRaises(ValueError):
            score_token(
                liquidity_usd=D(1),
                volume_24h_usd=D(1),
                risk_score=D(1),
                rsi_value=D(50),
                phase="NOT_A_PHASE",
            )

    def test_safety_weight_reduces_score_as_risk_rises(self):
        low = score_token(
            liquidity_usd=D(50000),
            volume_24h_usd=D(50000),
            risk_score=D(10),
            rsi_value=D(55),
        )
        high = score_token(
            liquidity_usd=D(50000),
            volume_24h_usd=D(50000),
            risk_score=D(90),
            rsi_value=D(55),
        )
        self.assertGreater(low.total, high.total)


if __name__ == "__main__":
    unittest.main()
