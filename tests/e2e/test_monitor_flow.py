"""End-to-end: the real pipeline under the monitor, fully offline (fixtures, no sockets)."""

from __future__ import annotations

import unittest

from bangzen_prime.application.api_budget_defaults import default_budget_registry
from bangzen_prime.application.monitor import Monitor
from tests.e2e.test_scan_flow import World, build
from tests.support import TOKEN_MINT


class FakeHolderData:
    def holder_profile(self, chain, mint):
        from decimal import Decimal
        from types import SimpleNamespace

        return SimpleNamespace(
            mint=mint,
            holder_count=500,
            top_holder_share_pct=Decimal("18.5"),
            source="solana_tracker",
            top_holders=tuple(f"H{i}" for i in range(5)),
        )


class MonitorEndToEndTest(unittest.TestCase):
    def test_monitor_runs_real_pipeline_and_respects_the_budget(self):
        container, _, transport, clock = build(world=World())
        now = [0.0]
        budget = default_budget_registry(lambda: now[0], scans_per_minute=3)
        monitor = Monitor(
            scan=container.scan,
            worker=container.worker,
            budget=budget,
            watchlist=(TOKEN_MINT,),
        )
        reports = monitor.run(
            cycles=5, interval_seconds=0, sleep=lambda s: clock.advance(91)
        )
        scanned = sum(r.scanned for r in reports)
        # Budget of 3 per minute with the clock frozen: exactly 3 real scans, the rest skipped.
        self.assertEqual(scanned, 3)
        self.assertEqual(sum(r.skipped_budget for r in reports), 2)
        self.assertEqual(
            sum(
                1
                for call in transport.calls
                if call.startswith("https://api.dexscreener.com")
            ),
            3,
        )

    def test_monitor_accepts_signals_once_history_exists_and_drains_outbox(self):
        container, _, _, clock = build(world=World())
        now = [0.0]
        budget = default_budget_registry(lambda: now[0], scans_per_minute=1000)
        monitor = Monitor(
            scan=container.scan,
            worker=container.worker,
            budget=budget,
            watchlist=(TOKEN_MINT,),
        )
        reports = monitor.run(
            cycles=25, interval_seconds=0, sleep=lambda s: clock.advance(91)
        )
        self.assertGreaterEqual(sum(r.accepted for r in reports), 1)
        pending = container.db.query_one(
            "SELECT COUNT(*) AS n FROM outbox WHERE status = 'PENDING'"
        )["n"]
        self.assertEqual(pending, 0)


if __name__ == "__main__":
    unittest.main()
