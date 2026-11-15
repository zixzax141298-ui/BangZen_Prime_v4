"""Monitor tests: budget enforcement, phase transitions, watchlist validation. No network."""

from __future__ import annotations

import os
import tempfile
import unittest

from bangzen_prime.core.errors import ConfigurationError
from bangzen_prime.core.monitor import MAX_WATCHLIST, Monitor, load_watchlist
from bangzen_prime.core.use_cases import ScanResult
from bangzen_prime.data.api_budget_defaults import default_budget_registry

MINTS = (
    "So11111111111111111111111111111111111111112",
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
    "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB",
)


class Clock:
    def __init__(self) -> None:
        self.t = 0.0

    def __call__(self) -> float:
        return self.t


class FakeScan:
    """Returns a scripted phase per mint per call. Records every call."""

    def __init__(self, phases: dict[str, list[str]], status: str = "REJECTED") -> None:
        self.phases = {m: list(seq) for m, seq in phases.items()}
        self.status = status
        self.calls: list[str] = []

    def execute(self, chain, mints):
        mint = mints[0]
        self.calls.append(mint)
        seq = self.phases.get(mint, ["UNKNOWN"])
        phase = seq.pop(0) if len(seq) > 1 else seq[0]
        return [ScanResult(mint, self.status, (), None, None, phase)]


class FakeWorker:
    def __init__(self) -> None:
        self.runs = 0

    def run_once(self, limit: int = 20):
        self.runs += 1


def monitor_with(scan, clock, per_minute=2, mints=MINTS):
    return Monitor(
        scan=scan,
        worker=FakeWorker(),
        budget=default_budget_registry(clock, scans_per_minute=per_minute),
        watchlist=mints,
    )


class BudgetInMonitorTests(unittest.TestCase):
    def test_per_minute_budget_caps_scans_and_skips_the_rest(self):
        clock = Clock()
        scan = FakeScan({})
        m = monitor_with(scan, clock, per_minute=2)
        report = m.run_cycle()
        self.assertEqual((report.scanned, report.skipped_budget), (2, 1))
        self.assertEqual(scan.calls, [MINTS[0], MINTS[1]])

    def test_same_minute_repeat_cycles_do_not_spend_api_calls(self):
        clock = Clock()
        scan = FakeScan({})
        m = monitor_with(scan, clock, per_minute=2)
        m.run_cycle()
        report = m.run_cycle()  # same instant: budget is exhausted
        self.assertEqual(report.scanned, 0)
        self.assertEqual(len(scan.calls), 2)

    def test_budget_refills_after_a_minute(self):
        clock = Clock()
        scan = FakeScan({})
        m = monitor_with(scan, clock, per_minute=2)
        m.run_cycle()
        clock.t = 60.0
        self.assertEqual(m.run_cycle().scanned, 2)


class PhaseTransitionTests(unittest.TestCase):
    def test_phase_change_between_cycles_is_recorded_once(self):
        clock = Clock()
        scan = FakeScan(
            {MINTS[0]: ["LAUNCH", "EARLY", "EARLY", "GROWTH"]}, status="REJECTED"
        )
        m = monitor_with(scan, clock, per_minute=10, mints=(MINTS[0],))
        seen = []
        for _ in range(4):
            seen.extend(m.run_cycle().transitions)
            clock.t += 1
        self.assertEqual(
            [(t.old, t.new) for t in seen], [("LAUNCH", "EARLY"), ("EARLY", "GROWTH")]
        )

    def test_outbox_is_drained_every_cycle(self):
        clock = Clock()
        worker = FakeWorker()
        m = Monitor(
            scan=FakeScan({}),
            worker=worker,
            budget=default_budget_registry(clock, scans_per_minute=10),
            watchlist=MINTS[:1],
        )
        m.run_cycle()
        m.run_cycle()
        self.assertEqual(worker.runs, 2)

    def test_run_respects_cycle_count_and_sleeps_between_cycles_only(self):
        clock = Clock()
        sleeps = []
        m = monitor_with(FakeScan({}), clock, per_minute=10, mints=MINTS[:1])
        reports = m.run(cycles=3, interval_seconds=15, sleep=sleeps.append)
        self.assertEqual(len(reports), 3)
        self.assertEqual(sleeps, [15, 15])  # no sleep after the final cycle


class WatchlistTests(unittest.TestCase):
    def _file(self, text: str) -> str:
        fd, path = tempfile.mkstemp(suffix=".txt")
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        self.addCleanup(os.unlink, path)
        return path

    def test_comments_blanks_and_duplicates_are_handled(self):
        path = self._file(f"# watch\n\n{MINTS[0]}\n{MINTS[0]}\n{MINTS[1]}\n")
        self.assertEqual(load_watchlist(path), (MINTS[0], MINTS[1]))

    def test_invalid_mint_fails_the_whole_file(self):
        with self.assertRaises(Exception):
            load_watchlist(self._file(f"{MINTS[0]}\n../../evil\n"))

    def test_empty_and_oversized_watchlists_are_rejected(self):
        with self.assertRaises(ConfigurationError):
            load_watchlist(self._file("# nothing\n"))
        import itertools

        alphabet = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
        combos = (
            MINTS[0][:-2] + a + b for a, b in itertools.product(alphabet, repeat=2)
        )
        big = "\n".join(
            itertools.islice(combos, MAX_WATCHLIST + 1)
        )  # 201 distinct, valid-length mints
        with self.assertRaises(ConfigurationError):
            load_watchlist(self._file(big))

    def test_monitor_refuses_an_empty_watchlist(self):
        with self.assertRaises(ConfigurationError):
            monitor_with(FakeScan({}), Clock(), mints=())


if __name__ == "__main__":
    unittest.main()
