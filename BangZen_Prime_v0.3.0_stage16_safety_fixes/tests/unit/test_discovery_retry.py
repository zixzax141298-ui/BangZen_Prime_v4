import unittest

from bangzen_prime.core.use_cases import ScanResult
from bangzen_prime.discovery.scanner import ContinuousDiscoveryUseCase
from tests.support import TOKEN_MINT


class Feed:
    def fetch_candidates(self, limit=30):
        return [TOKEN_MINT]


class Scanner:
    def __init__(self, reasons):
        self.reasons = reasons
        self.calls = 0

    def execute(self, chain, mints):
        if mints:
            self.calls += 1
        return [
            ScanResult(mint, "REJECTED", self.reasons, None, None, "LAUNCH")
            for mint in mints
        ]


class DiscoveryRetryTests(unittest.TestCase):
    def test_missing_pair_and_insufficient_history_are_rechecked_quickly(self):
        for reason in ("EMPTY_MARKET", "INSUFFICIENT_HISTORY", "SAFETY_UNAVAILABLE"):
            with self.subTest(reason=reason):
                now = [10.0]
                scanner = Scanner((reason,))
                discovery = ContinuousDiscoveryUseCase(
                    feed=Feed(),
                    scanner=scanner,
                    clock=lambda: now[0],
                    dedupe_seconds=1800,
                    retry_seconds=60,
                )
                discovery.execute()
                now[0] = 69.0
                self.assertEqual(discovery.execute().scanned, 0)
                now[0] = 70.0
                self.assertEqual(discovery.execute().scanned, 1)
                self.assertEqual(scanner.calls, 2)

    def test_non_transient_risk_rejection_keeps_normal_cooldown(self):
        now = [10.0]
        scanner = Scanner(("RUGGED",))
        discovery = ContinuousDiscoveryUseCase(
            feed=Feed(),
            scanner=scanner,
            clock=lambda: now[0],
            dedupe_seconds=1800,
            retry_seconds=60,
        )
        discovery.execute()
        now[0] = 70.0
        self.assertEqual(discovery.execute().scanned, 0)
        self.assertEqual(scanner.calls, 1)


if __name__ == "__main__":
    unittest.main()
