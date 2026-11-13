import unittest
from datetime import UTC, datetime, timedelta

from bangzen_prime.application.lifecycle import TokenPhase, assess_token_phase


NOW = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)


class TokenLifecyclePhaseTests(unittest.TestCase):
    def test_missing_pair_creation_time_is_unknown_not_rejected(self):
        result = assess_token_phase(None, NOW)
        self.assertIs(result.phase, TokenPhase.UNKNOWN)
        self.assertIsNone(result.pair_age_seconds)

    def test_launch_phase_and_fast_refresh(self):
        result = assess_token_phase(NOW - timedelta(minutes=5), NOW)
        self.assertIs(result.phase, TokenPhase.LAUNCH)
        self.assertEqual(result.suggested_refresh_seconds, 15)

    def test_early_growth_and_mature_boundaries(self):
        cases = [
            (timedelta(hours=2), TokenPhase.EARLY, 60),
            (timedelta(days=2), TokenPhase.GROWTH, 300),
            (timedelta(days=10), TokenPhase.MATURE, 900),
        ]
        for age, phase, refresh in cases:
            with self.subTest(age=age):
                result = assess_token_phase(NOW - age, NOW)
                self.assertIs(result.phase, phase)
                self.assertEqual(result.suggested_refresh_seconds, refresh)

    def test_future_pair_timestamp_is_unknown(self):
        result = assess_token_phase(NOW + timedelta(minutes=1), NOW)
        self.assertIs(result.phase, TokenPhase.UNKNOWN)

    def test_cex_phase_requires_explicit_verified_evidence(self):
        result = assess_token_phase(None, NOW, verified_cex_listing=True)
        self.assertIs(result.phase, TokenPhase.CEX_LISTED)


if __name__ == "__main__":
    unittest.main()
