import json
import logging
import os
import tempfile
import unittest
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from bangzen_prime.core import resource_guard
from bangzen_prime.core.health import DEGRADED, HALTED, OK, build_health
from bangzen_prime.core.heartbeat import HeartbeatRegistry
from bangzen_prime.core.log_files import configure_file_logging
from bangzen_prime.core.observability.metrics import Metrics
from bangzen_prime.core.supervisor import Supervisor, WorkerSpec
from bangzen_prime.discovery.cooldown_store import CooldownStore
from bangzen_prime.discovery.scanner import ContinuousDiscoveryUseCase

MINT = "So11111111111111111111111111111111111111112"
NOW = datetime(2026, 11, 15, 12, 0, tzinfo=UTC)


class Clock:
    def __init__(self, value: float = 0.0) -> None:
        self.value = value

    def __call__(self) -> float:
        return self.value


@dataclass
class _Result:
    mint: str
    reasons: tuple = ()


class _Feed:
    def __init__(self, mints):
        self._mints = mints

    def fetch_candidates(self, limit: int = 30):
        return list(self._mints)


class _Scanner:
    def __init__(self):
        self.calls: list[list[str]] = []

    def execute(self, chain, mints):
        self.calls.append(list(mints))
        return [_Result(m) for m in mints]


class CooldownStoreTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_round_trip_keeps_only_unexpired_entries(self):
        store = CooldownStore(self.dir / "cool.json")
        store.save({"a": 2000.0, "b": 500.0}, now_epoch=1000.0)
        self.assertEqual(store.load(1000.0), {"a": 2000.0})
        self.assertEqual(store.load(2500.0), {})

    def test_missing_corrupt_or_wrong_version_file_means_no_cooldowns(self):
        path = self.dir / "cool.json"
        self.assertEqual(CooldownStore(path).load(0.0), {})
        path.write_text("{not json", encoding="utf-8")
        self.assertEqual(CooldownStore(path).load(0.0), {})
        path.write_text(json.dumps({"version": 99, "entries": {"a": 9e9}}), encoding="utf-8")
        self.assertEqual(CooldownStore(path).load(0.0), {})

    def test_non_numeric_expiry_is_ignored(self):
        path = self.dir / "cool.json"
        path.write_text(json.dumps({"version": 1, "entries": {"a": "x", "b": True, "c": 5e9}}),
                        encoding="utf-8")
        self.assertEqual(CooldownStore(path).load(0.0), {"c": 5e9})

    def test_save_is_atomic_and_leaves_no_temporary_files(self):
        target = self.dir / "nested" / "cool.json"
        CooldownStore(target).save({"a": 9e9}, now_epoch=0.0)
        self.assertEqual(sorted(os.listdir(target.parent)), ["cool.json"])


class DiscoveryRestartTest(unittest.TestCase):
    def test_cooldown_survives_restart_and_expires_on_schedule(self):
        with tempfile.TemporaryDirectory() as tmp:
            store_path = Path(tmp) / "cool.json"
            scanner = _Scanner()
            first = ContinuousDiscoveryUseCase(
                feed=_Feed([MINT]), scanner=scanner, clock=Clock(0.0),
                cooldown_store=CooldownStore(store_path), epoch_clock=Clock(1000.0),
                dedupe_seconds=1800,
            )
            first.execute(limit=5)
            self.assertEqual(scanner.calls, [[MINT]])

            # Restart 100 s later: monotonic clock restarts at 0, wall clock moved on.
            scanner2 = _Scanner()
            second = ContinuousDiscoveryUseCase(
                feed=_Feed([MINT]), scanner=scanner2, clock=Clock(0.0),
                cooldown_store=CooldownStore(store_path), epoch_clock=Clock(1100.0),
                dedupe_seconds=1800,
            )
            cycle = second.execute(limit=5)
            self.assertEqual(scanner2.calls, [])
            self.assertEqual(cycle.skipped_recent, 1)

            # After the dedupe window has passed, the candidate is scanned again.
            scanner3 = _Scanner()
            third = ContinuousDiscoveryUseCase(
                feed=_Feed([MINT]), scanner=scanner3, clock=Clock(0.0),
                cooldown_store=CooldownStore(store_path), epoch_clock=Clock(3000.0),
                dedupe_seconds=1800,
            )
            third.execute(limit=5)
            self.assertEqual(scanner3.calls, [[MINT]])

    def test_without_store_behaviour_is_unchanged(self):
        scanner = _Scanner()
        use_case = ContinuousDiscoveryUseCase(feed=_Feed([MINT]), scanner=scanner, clock=Clock(0.0))
        use_case.execute(limit=5)
        use_case.execute(limit=5)
        self.assertEqual(scanner.calls, [[MINT]])


class SupervisorBackoffTest(unittest.TestCase):
    def _supervisor(self, run, clock, **kwargs):
        worker = WorkerSpec("flaky", run)
        sup = Supervisor(
            workers=[worker],
            emergency_stop=lambda: False,
            metrics=Metrics(),
            sleep=lambda s: None,
            clock=clock,
            **kwargs,
        )
        return sup, worker

    def test_failed_worker_waits_exponentially_before_running_again(self):
        clock = Clock(0.0)
        calls = []

        def run():
            calls.append(clock.value)
            raise RuntimeError("boom")

        sup, worker = self._supervisor(run, clock, backoff_base_seconds=10, max_consecutive_failures=10)
        self.assertEqual(sup.run_cycle()["flaky"], "FAILED")  # t=0, next at 10
        clock.value = 5
        self.assertEqual(sup.run_cycle()["flaky"], "BACKOFF")
        clock.value = 10
        self.assertEqual(sup.run_cycle()["flaky"], "FAILED")  # second failure, next at 10+20
        clock.value = 29
        self.assertEqual(sup.run_cycle()["flaky"], "BACKOFF")
        clock.value = 30
        self.assertEqual(sup.run_cycle()["flaky"], "FAILED")
        self.assertEqual(calls, [0, 10, 30])

    def test_backoff_is_capped(self):
        clock = Clock(0.0)
        sup, _ = self._supervisor(lambda: None, clock, backoff_base_seconds=10, backoff_max_seconds=60)
        self.assertEqual(sup._backoff_for(1), 10)
        self.assertEqual(sup._backoff_for(3), 40)
        self.assertEqual(sup._backoff_for(10), 60)

    def test_default_has_no_backoff_so_existing_behaviour_is_kept(self):
        clock = Clock(0.0)
        calls = []

        def run():
            calls.append(1)
            raise RuntimeError("boom")

        sup, _ = self._supervisor(run, clock)
        sup.run_cycle()
        self.assertEqual(sup.run_cycle()["flaky"], "FAILED")
        self.assertEqual(len(calls), 2)

    def test_negative_backoff_is_rejected(self):
        with self.assertRaises(ValueError):
            Supervisor(workers=[], emergency_stop=lambda: False, metrics=Metrics(),
                       sleep=lambda s: None, backoff_base_seconds=-1)


class MemoryGuardTest(unittest.TestCase):
    def _sup(self, reader, order_worker=False):
        ran = []
        workers = [
            WorkerSpec("scan", lambda: ran.append("scan")),
            WorkerSpec("trade", lambda: ran.append("trade"), places_orders=True),
        ]
        sup = Supervisor(workers=workers, emergency_stop=lambda: False, metrics=Metrics(),
                         sleep=lambda s: None, memory_limit_mb=500, rss_reader=reader)
        return sup, ran

    def test_over_limit_pauses_non_order_workers_only(self):
        sup, ran = self._sup(lambda: 900.0)
        results = sup.run_cycle()
        self.assertEqual(results["scan"], "SKIPPED_MEMORY")
        self.assertEqual(results["trade"], "OK")
        self.assertEqual(ran, ["trade"])

    def test_under_limit_runs_everything(self):
        sup, ran = self._sup(lambda: 100.0)
        self.assertEqual(sup.run_cycle(), {"scan": "OK", "trade": "OK"})

    def test_unknown_memory_does_not_pause_workers(self):
        sup, ran = self._sup(lambda: None)
        self.assertEqual(sup.run_cycle(), {"scan": "OK", "trade": "OK"})

    def test_memory_status_values(self):
        self.assertEqual(resource_guard.memory_status(500, lambda: 100.0), resource_guard.OK)
        self.assertEqual(resource_guard.memory_status(500, lambda: 600.0), resource_guard.OVER_LIMIT)
        self.assertEqual(resource_guard.memory_status(500, lambda: None), resource_guard.UNKNOWN)
        with self.assertRaises(ValueError):
            resource_guard.memory_status(0, lambda: 1.0)

    def test_rss_reader_handles_missing_proc_file(self):
        self.assertIsNone(resource_guard.current_rss_mb("/nonexistent/proc/status"))


class HealthReportTest(unittest.TestCase):
    def _sup(self):
        return Supervisor(
            workers=[WorkerSpec("scan", lambda: None), WorkerSpec("ai", lambda: None)],
            emergency_stop=lambda: False, metrics=Metrics(), sleep=lambda s: None,
        )

    def test_ok_when_everything_is_healthy(self):
        sup = self._sup()
        beats = HeartbeatRegistry()
        beats.beat("scan", NOW)
        beats.beat("ai", NOW)
        report = build_health(sup, now=NOW, heartbeats=beats, halt_path="/nonexistent/HALT.flag")
        self.assertEqual(report.status, OK)
        self.assertEqual(report.memory, resource_guard.UNKNOWN)

    def test_halt_flag_or_emergency_stop_is_halted(self):
        sup = self._sup()
        self.assertEqual(build_health(sup, now=NOW, halt_path="/nonexistent/HALT.flag",
                                      emergency_stop=True).status, HALTED)
        with tempfile.TemporaryDirectory() as tmp:
            flag = Path(tmp) / "HALT.flag"
            flag.write_text("stop", encoding="utf-8")
            self.assertEqual(build_health(sup, now=NOW, halt_path=str(flag)).status, HALTED)

    def test_disabled_worker_or_stale_heartbeat_is_degraded(self):
        sup = self._sup()
        sup.workers[1].disabled = True
        self.assertEqual(build_health(sup, now=NOW, halt_path="/nonexistent/x").status, DEGRADED)

        sup2 = self._sup()
        beats = HeartbeatRegistry()
        beats.beat("scan", NOW - timedelta(hours=1))
        beats.beat("ai", NOW)
        report = build_health(sup2, now=NOW, heartbeats=beats, halt_path="/nonexistent/x")
        self.assertEqual(report.stale_workers, ("scan",))
        self.assertEqual(report.status, DEGRADED)

    def test_memory_over_limit_is_degraded_but_unknown_memory_is_not(self):
        sup = self._sup()
        over = build_health(sup, now=NOW, halt_path="/nonexistent/x", memory_limit_mb=100,
                            rss_reader=lambda: 500.0)
        self.assertEqual(over.status, DEGRADED)
        unknown = build_health(sup, now=NOW, halt_path="/nonexistent/x", memory_limit_mb=100,
                               rss_reader=lambda: None)
        self.assertEqual(unknown.status, OK)
        self.assertEqual(unknown.memory, resource_guard.UNKNOWN)

    def test_report_is_serialisable(self):
        report = build_health(self._sup(), now=NOW, halt_path="/nonexistent/x")
        self.assertEqual(json.loads(json.dumps(report.as_dict()))["status"], OK)

    def test_non_positive_stale_window_is_rejected(self):
        with self.assertRaises(ValueError):
            build_health(self._sup(), now=NOW, stale_after=timedelta(0))


class FileLoggingTest(unittest.TestCase):
    def tearDown(self):
        logger = logging.getLogger("bangzen_prime")
        for handler in list(logger.handlers):
            handler.close()
        logger.handlers.clear()

    def test_rotation_caps_number_of_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bot.log"
            configure_file_logging(path, max_bytes=1024, backup_count=2)
            log = logging.getLogger("bangzen_prime.test")
            for i in range(400):
                log.info("line %d %s", i, "x" * 40)
            for handler in logging.getLogger("bangzen_prime").handlers:
                handler.flush()
            files = sorted(os.listdir(tmp))
            self.assertLessEqual(len(files), 3)
            self.assertIn("bot.log", files)
            self.assertIn("bot.log.1", files)
            self.assertNotIn("bot.log.3", files)

    def test_invalid_rotation_settings_are_rejected(self):
        with self.assertRaises(ValueError):
            configure_file_logging("/tmp/x.log", max_bytes=10)
        with self.assertRaises(ValueError):
            configure_file_logging("/tmp/x.log", backup_count=-1)


if __name__ == "__main__":
    unittest.main()
