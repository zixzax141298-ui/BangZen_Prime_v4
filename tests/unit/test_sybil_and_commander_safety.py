from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from bangzen_prime.application.ai_commander import AICommander
from bangzen_prime.infrastructure.adapters.onchain.sybil_adapter import SybilAdapter


class FakeAsyncClient:
    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False


class SybilAdapterEvidenceTests(unittest.TestCase):
    def run_report(self, outcomes):
        adapter = SybilAdapter("https://example.invalid", timeout=1)

        async def find_funder(_client, holder):
            return outcomes[holder]

        adapter._find_funder = find_funder
        with patch(
            "bangzen_prime.infrastructure.adapters.onchain.sybil_adapter.httpx.AsyncClient",
            return_value=FakeAsyncClient(),
        ):
            return asyncio.run(
                adapter.check_sybil_cluster(
                    "ignored-mint",
                    [{"address": key} for key in outcomes],
                )
            )

    def test_all_observations_without_cluster_are_explicitly_clear(self):
        report = self.run_report(
            {
                "wallet-a": ("SELF", None),
                "wallet-b": ("SELF", None),
                "wallet-c": ("SELF", None),
            }
        )
        self.assertTrue(report.available)
        self.assertIs(report.is_bundled, False)
        self.assertEqual(report.reason, "safe_no_cluster")

    def test_unavailable_funder_data_is_unknown_not_bundled(self):
        report = self.run_report(
            {
                "wallet-a": ("UNAVAILABLE", None),
                "wallet-b": ("SELF", None),
                "wallet-c": ("SELF", None),
            }
        )
        self.assertFalse(report.available)
        self.assertIsNone(report.is_bundled)
        self.assertEqual(report.reason, "funder_evidence_incomplete")

    def test_confirmed_cluster_remains_positive_even_with_other_unknowns(self):
        report = self.run_report(
            {
                "wallet-a": ("FUNDED", "funder-x"),
                "wallet-b": ("FUNDED", "funder-x"),
                "wallet-c": ("FUNDED", "funder-x"),
                "wallet-d": ("UNAVAILABLE", None),
            }
        )
        self.assertTrue(report.available)
        self.assertIs(report.is_bundled, True)
        self.assertEqual(report.cluster_size, 3)
        self.assertEqual(report.unavailable_count, 1)

    def test_missing_optional_helius_configuration_is_unavailable(self):
        report = asyncio.run(
            SybilAdapter("").check_sybil_cluster(
                "ignored-mint",
                [
                    {"address": "wallet-a"},
                    {"address": "wallet-b"},
                    {"address": "wallet-c"},
                ],
            )
        )
        self.assertFalse(report.available)
        self.assertIsNone(report.is_bundled)
        self.assertEqual(report.reason, "provider_not_configured")

    def test_too_few_holders_is_unknown(self):
        report = asyncio.run(
            SybilAdapter("https://example.invalid").check_sybil_cluster(
                "ignored-mint", [{"address": "wallet-a"}, {"address": "wallet-b"}]
            )
        )
        self.assertFalse(report.available)
        self.assertIsNone(report.is_bundled)
        self.assertEqual(report.reason, "insufficient_holder_evidence")


class FakeHoneypot:
    def __init__(self, report):
        self.report = report

    async def check_honeypot(self, mint, force=False):
        self.assert_forced = force
        return self.report


class FakeSybil:
    async def check_sybil_cluster(self, mint, holders):
        return SimpleNamespace(available=True, is_bundled=False)


class FakeBrain:
    def __init__(self):
        self.calls = 0

    def decide(self, context):
        self.calls += 1
        return SimpleNamespace(decision="WATCH", reason="test", source="fake")


class AICommanderHoneypotGateTests(unittest.TestCase):
    def commander(self, report):
        brain = FakeBrain()
        commander = AICommander(
            brain=brain,
            sybil=FakeSybil(),
            honeypot=FakeHoneypot(report),
            news=object(),
            radar=object(),
            lp_sniper=object(),
            smart_money=object(),
        )
        return commander, brain

    def test_unavailable_honeypot_check_blocks_ai(self):
        commander, brain = self.commander(
            SimpleNamespace(available=False, is_honeypot=None, is_safe=False)
        )
        result = asyncio.run(commander.execute("mint-address", object(), {}, {}))
        self.assertEqual(result.decision, "SKIP")
        self.assertEqual(result.reason, "honeypot_check_unavailable")
        self.assertEqual(brain.calls, 0)

    def test_non_explicit_safe_result_blocks_ai(self):
        commander, brain = self.commander(
            SimpleNamespace(available=True, is_honeypot=None, is_safe=False)
        )
        result = asyncio.run(commander.execute("mint-address", object(), {}, {}))
        self.assertEqual(result.decision, "SKIP")
        self.assertEqual(result.reason, "honeypot_not_cleared")
        self.assertEqual(brain.calls, 0)

    def test_explicit_safe_result_allows_advisory_ai_call(self):
        commander, brain = self.commander(
            SimpleNamespace(available=True, is_honeypot=False, is_safe=True)
        )
        result = asyncio.run(
            commander.execute(
                "mint-address",
                object(),
                {},
                {
                    "top_holders": [
                        {"address": "wallet-a"},
                        {"address": "wallet-b"},
                        {"address": "wallet-c"},
                    ]
                },
            )
        )
        self.assertEqual(result.decision, "WATCH")
        self.assertEqual(brain.calls, 1)


if __name__ == "__main__":
    unittest.main()
