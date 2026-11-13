from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from bangzen_prime.application.ai_commander import AICommander


class FakeSybil:
    def __init__(self, report=None, error=None):
        self.report = report
        self.error = error
        self.calls = []

    async def check_sybil_cluster(self, mint, top_holders):
        self.calls.append((mint, top_holders))
        if self.error:
            raise self.error
        return self.report


class FakeHoneypot:
    async def check_honeypot(self, mint, force=False):
        return SimpleNamespace(
            available=True,
            is_honeypot=False,
            is_safe=True,
        )


class FakeBrain:
    def __init__(self):
        self.calls = 0

    def decide(self, context):
        self.calls += 1
        return SimpleNamespace(decision="WATCH", reason="test", source="fake")


def make_commander(sybil):
    brain = FakeBrain()
    commander = AICommander(
        brain=brain,
        sybil=sybil,
        honeypot=FakeHoneypot(),
        news=object(),
        radar=object(),
        lp_sniper=object(),
        smart_money=object(),
    )
    return commander, brain


class AICommanderSybilGateTests(unittest.TestCase):
    def setUp(self):
        self.context = object()
        self.holders = [{"address": "wallet-a"}, {"address": "wallet-b"}, {"address": "wallet-c"}]

    def test_missing_holder_evidence_blocks_before_provider_or_ai(self):
        sybil = FakeSybil(
            report=SimpleNamespace(available=True, is_bundled=False)
        )
        commander, brain = make_commander(sybil)

        result = asyncio.run(commander.execute("mint-address", self.context, {}, {}))

        self.assertEqual(result.decision, "SKIP")
        self.assertEqual(result.reason, "sybil_holder_evidence_unavailable")
        self.assertEqual(sybil.calls, [])
        self.assertEqual(brain.calls, 0)

    def test_unavailable_sybil_evidence_blocks_ai(self):
        sybil = FakeSybil(
            report=SimpleNamespace(available=False, is_bundled=None)
        )
        commander, brain = make_commander(sybil)

        result = asyncio.run(
            commander.execute(
                "mint-address", self.context, {}, {"top_holders": self.holders}
            )
        )

        self.assertEqual(result.decision, "SKIP")
        self.assertEqual(result.reason, "sybil_check_unavailable")
        self.assertEqual(brain.calls, 0)

    def test_confirmed_shared_funder_cluster_blocks_ai(self):
        sybil = FakeSybil(
            report=SimpleNamespace(available=True, is_bundled=True)
        )
        commander, brain = make_commander(sybil)

        result = asyncio.run(
            commander.execute(
                "mint-address", self.context, {}, {"top_holders": self.holders}
            )
        )

        self.assertEqual(result.decision, "SKIP")
        self.assertEqual(result.reason, "sybil_cluster_detected")
        self.assertEqual(brain.calls, 0)

    def test_provider_exception_blocks_ai(self):
        sybil = FakeSybil(error=RuntimeError("provider down"))
        commander, brain = make_commander(sybil)

        result = asyncio.run(
            commander.execute(
                "mint-address", self.context, {}, {"top_holders": self.holders}
            )
        )

        self.assertEqual(result.decision, "SKIP")
        self.assertEqual(result.reason, "sybil_check_unavailable")
        self.assertEqual(brain.calls, 0)

    def test_only_explicit_clear_sybil_result_allows_honeypot_and_ai(self):
        sybil = FakeSybil(
            report=SimpleNamespace(available=True, is_bundled=False)
        )
        commander, brain = make_commander(sybil)

        result = asyncio.run(
            commander.execute(
                "mint-address", self.context, {}, {"top_holders": self.holders}
            )
        )

        self.assertEqual(result.decision, "WATCH")
        self.assertEqual(brain.calls, 1)
        self.assertEqual(sybil.calls, [("mint-address", self.holders)])


if __name__ == "__main__":
    unittest.main()
