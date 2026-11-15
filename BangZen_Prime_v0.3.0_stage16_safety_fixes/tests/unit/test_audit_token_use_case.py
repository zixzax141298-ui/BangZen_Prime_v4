from __future__ import annotations

import asyncio
import unittest
from decimal import Decimal

from bangzen_prime.core.errors import DomainError
from bangzen_prime.core.use_cases import AuditTokenUseCase
from bangzen_prime.discovery.tokens import SafetyAssessment
from tests.support import START, TOKEN_MINT


class FakeSafety:
    def __init__(self, assessment):
        self.assessment = assessment
        self.calls = []

    def fetch_safety(self, chain, mint):
        self.calls.append((chain, mint))
        return self.assessment


def assessment(chain="solana", mint=TOKEN_MINT):
    return SafetyAssessment.create(
        chain=chain,
        mint=mint,
        risk_score=Decimal(12),
        rugged=False,
        source="fake",
        checked_at=START,
    )


class AuditTokenUseCaseTest(unittest.TestCase):
    def test_returns_assessment_for_exact_requested_identity(self):
        safety = FakeSafety(assessment())
        result = asyncio.run(
            AuditTokenUseCase(safety).execute_async("solana", TOKEN_MINT)
        )
        self.assertEqual(result, safety.assessment)
        self.assertEqual(safety.calls, [("solana", TOKEN_MINT)])

    def test_rejects_assessment_for_different_mint(self):
        safety = FakeSafety(
            assessment(mint="So11111111111111111111111111111111111111112")
        )
        with self.assertRaises(DomainError):
            asyncio.run(AuditTokenUseCase(safety).execute_async("solana", TOKEN_MINT))

    def test_rejects_non_assessment_provider_result(self):
        safety = FakeSafety({"risk_score": 0})
        with self.assertRaises(DomainError):
            asyncio.run(AuditTokenUseCase(safety).execute_async("solana", TOKEN_MINT))

    def test_propagates_provider_failure_for_scan_fail_closed_handling(self):
        class BrokenSafety:
            def fetch_safety(self, chain, mint):
                raise RuntimeError("provider unavailable")

        with self.assertRaises(RuntimeError):
            asyncio.run(
                AuditTokenUseCase(BrokenSafety()).execute_async("solana", TOKEN_MINT)
            )


if __name__ == "__main__":
    unittest.main()
