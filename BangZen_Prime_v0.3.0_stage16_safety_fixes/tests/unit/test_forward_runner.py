import json
import tempfile
import unittest
from pathlib import Path

from bangzen_prime.core.bootstrap import build_container
from bangzen_prime.core.config import Settings
from bangzen_prime.core.errors import ConfigurationError, DomainError
from bangzen_prime.core.forward_runner import (
    ForwardRunSettings,
    build_forward_paper,
    run_forward_paper,
)
from bangzen_prime.core.interfaces.demo import (
    DEMO_MINT,
    OfflineMarket,
    _LogSink,
    _OfflineHolders,
    _OfflineIntel,
)


def _container(settings: Settings):
    container = build_container(
        settings,
        transport=OfflineMarket(),
        notifier=_LogSink(),
        db_path=":memory:",
        sleep=lambda s: None,
    )
    container.scan.holder_data = _OfflineHolders()
    container.scan.intel_adapter = _OfflineIntel()
    return container


class ForwardRunnerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.watchlist = root / "watch.txt"
        self.watchlist.write_text(DEMO_MINT + "\n", encoding="utf-8")
        self.ledger = root / "forward.jsonl"

    def tearDown(self):
        self.tmp.cleanup()

    def _run(self, settings, **overrides):
        values = dict(watchlist_path=str(self.watchlist), ledger_path=str(self.ledger),
                      interval_seconds=15, cycles=2, scans_per_minute=20)
        values.update(overrides)
        lines: list[str] = []
        results = run_forward_paper(
            _container(settings), settings, ForwardRunSettings(**values),
            sleep=lambda s: None, out=lines.append,
        )
        return results, lines

    def test_live_and_broadcast_are_refused(self):
        with self.assertRaises(ConfigurationError):
            Settings(db_path=":memory:", live_trading=True)
        with self.assertRaises(ConfigurationError):
            Settings(db_path=":memory:", broadcast_enabled=True)

    def test_argument_validation(self):
        for bad in (
            dict(interval_seconds=5),
            dict(scans_per_minute=0),
            dict(cycles=-1),
            dict(signal_max_age_seconds=10),
        ):
            with self.subTest(bad=bad):
                with self.assertRaises(ConfigurationError):
                    ForwardRunSettings(watchlist_path="w", ledger_path="l", **bad).validate()

    def test_halt_blocks_scans_and_orders(self):
        settings = Settings(db_path=":memory:", emergency_stop=True)
        results, lines = self._run(settings)
        self.assertEqual(results, [])
        self.assertEqual(json.loads(lines[0]), {"cycle": 1, "status": "HALTED"})
        container = _container(settings)
        self.assertEqual(container.db.query_one("SELECT COUNT(*) AS n FROM orders")["n"], 0)

    def test_without_spread_source_no_order_opens_and_ledger_is_written(self):
        settings = Settings(db_path=":memory:")
        results, lines = self._run(settings)
        self.assertEqual(len(results), 2)
        self.assertEqual(len(lines), 2)
        for cycle in results:
            self.assertEqual(cycle.opened, ())
            self.assertEqual(cycle.closed, 0)
        for line in lines:
            self.assertEqual(json.loads(line)["opened"], 0)
        self.assertTrue(self.ledger.exists())
        self.assertEqual(self.ledger.read_text(encoding="utf-8").count("\n"), 1)  # header only

    def test_same_config_can_be_resumed(self):
        settings = Settings(db_path=":memory:")
        self._run(settings, cycles=1)
        results, _ = self._run(settings, cycles=1)
        self.assertEqual(len(results), 1)

    def test_changed_frozen_config_is_refused_for_existing_ledger(self):
        self._run(Settings(db_path=":memory:"), cycles=1)
        changed = Settings(db_path=":memory:", max_risk_per_trade_pct=2)
        with self.assertRaises(DomainError):
            self._run(changed, cycles=1)

    def test_build_forward_paper_refuses_non_paper_settings(self):
        settings = Settings(db_path=":memory:")
        container = _container(settings)
        with self.assertRaises(ConfigurationError):
            build_forward_paper(container, Settings(db_path=":memory:", dry_run=False))


if __name__ == "__main__":
    unittest.main()
