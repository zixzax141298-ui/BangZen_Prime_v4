"""HALT.flag kill switch (AI_RULES non_negotiable_safety.halt_flag). Stdlib only, no network."""

import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from bangzen_prime.core.monitor import Monitor
from bangzen_prime.core.outbox_worker import OutboxWorker
from bangzen_prime.risk.emergency_stop import halt_engaged, halt_flag_engaged

MINT = "So11111111111111111111111111111111111111112"


class _Budget:
    def remaining(self, provider):
        return 10

    def try_acquire(self, provider):
        return True


class _Scan:
    def __init__(self):
        self.calls = []

    def execute(self, chain, mints):
        self.calls.append(tuple(mints))
        return [type("Result", (), {"status": "REJECTED", "phase": None})()]


class _Worker:
    def __init__(self):
        self.calls = 0

    def run_once(self):
        self.calls += 1


class _Bus:
    def __init__(self):
        self.dispatched = []

    def dispatch(self, event):
        self.dispatched.append(event)


class HaltFlagTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.flag = os.path.join(self.dir, "HALT.flag")

    def test_absent_flag_is_not_engaged(self):
        self.assertFalse(halt_flag_engaged(self.flag))

    def test_present_flag_is_engaged(self):
        open(self.flag, "w").close()
        self.assertTrue(halt_flag_engaged(self.flag))

    def test_undeterminable_state_fails_closed(self):
        # The parent is a regular file, so stat raises NotADirectoryError (an OSError).
        plain = os.path.join(self.dir, "plain")
        open(plain, "w").close()
        self.assertTrue(halt_flag_engaged(os.path.join(plain, "HALT.flag")))

    def test_environment_kill_switch_engages_without_file(self):
        self.assertTrue(halt_engaged(True, self.flag))
        self.assertFalse(halt_engaged(False, self.flag))


class MonitorHaltTests(unittest.TestCase):
    def _monitor(self, halt):
        scan, worker = _Scan(), _Worker()
        monitor = Monitor(
            scan=scan,
            worker=worker,
            budget=_Budget(),
            watchlist=(MINT,),
            halt_check=halt,
        )
        return monitor, scan, worker

    def test_halted_cycle_scans_nothing_and_drains_nothing(self):
        monitor, scan, worker = self._monitor(lambda: True)
        report = monitor.run_cycle()
        self.assertTrue(report.halted)
        self.assertEqual(report.scanned, 0)
        self.assertEqual(scan.calls, [])
        self.assertEqual(worker.calls, 0)

    def test_flag_engaged_mid_run_stops_later_cycles(self):
        state = {"halt": False}
        monitor, scan, worker = self._monitor(lambda: state["halt"])
        monitor.run_cycle()
        self.assertEqual(len(scan.calls), 1)
        state["halt"] = True
        report = monitor.run_cycle()
        self.assertTrue(report.halted)
        self.assertEqual(len(scan.calls), 1)
        self.assertEqual(worker.calls, 1)

    def test_clear_flag_resumes_normal_cycles(self):
        state = {"halt": True}
        monitor, scan, worker = self._monitor(lambda: state["halt"])
        monitor.run_cycle()
        state["halt"] = False
        report = monitor.run_cycle()
        self.assertFalse(report.halted)
        self.assertEqual(len(scan.calls), 1)
        self.assertEqual(worker.calls, 1)


class OutboxHaltTests(unittest.TestCase):
    def test_halted_worker_claims_and_dispatches_nothing(self):
        bus = _Bus()
        # db and clock are None: the halt check must return before either is touched.
        worker = OutboxWorker(
            db=None, bus=bus, clock=lambda: None, halt_check=lambda: True
        )
        stats = worker.run_once()
        self.assertEqual(stats.claimed, 0)
        self.assertEqual(bus.dispatched, [])


class CliHaltTests(unittest.TestCase):
    def test_monitor_refused_when_halt_flag_present(self):
        from bangzen_prime.core.interfaces import cli

        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "HALT.flag"), "w").close()
            previous = os.getcwd()
            os.chdir(d)
            try:
                err = io.StringIO()
                env = {"BANGZEN_EMERGENCY_STOP": "false"}
                with mock.patch.dict(os.environ, env), contextlib.redirect_stderr(err):
                    code = cli.main(
                        [
                            "monitor",
                            "--watchlist",
                            "watchlist.txt",
                            "--interval-seconds",
                            "60",
                        ]
                    )
            finally:
                os.chdir(previous)
        self.assertEqual(code, cli.EXIT_ERROR)
        self.assertIn("HALT.flag", err.getvalue())


if __name__ == "__main__":
    unittest.main()
