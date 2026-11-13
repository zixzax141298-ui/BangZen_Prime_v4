import unittest

from bangzen_prime.application.supervisor import Supervisor, WorkerSpec
from bangzen_prime.infrastructure.observability.metrics import Metrics


def sup(workers, emergency=False, sleeps=None):
    sleeps = sleeps if sleeps is not None else []
    return (
        Supervisor(
            workers=workers,
            emergency_stop=lambda: emergency,
            metrics=Metrics(),
            sleep=sleeps.append,
        ),
        sleeps,
    )


class SupervisorTest(unittest.TestCase):
    def test_failure_in_one_worker_does_not_stop_others(self):
        ran = []

        def bad():
            raise RuntimeError("boom")

        s, _ = sup([WorkerSpec("bad", bad), WorkerSpec("good", lambda: ran.append(1))])
        result = s.run_cycle()
        self.assertEqual(result, {"bad": "FAILED", "good": "OK"})
        self.assertEqual(ran, [1])

    def test_repeat_failures_disable_worker(self):
        def bad():
            raise RuntimeError("boom")

        s, _ = sup([WorkerSpec("bad", bad)])
        s.max_consecutive_failures = 2
        s.run_cycle()
        s.run_cycle()
        self.assertTrue(s.workers[0].disabled)
        self.assertEqual(s.run_cycle()["bad"], "DISABLED")

    def test_success_resets_failure_streak(self):
        calls = {"n": 0}

        def flaky():
            calls["n"] += 1
            if calls["n"] in (1, 3):
                raise RuntimeError("x")

        s, _ = sup([WorkerSpec("flaky", flaky)])
        s.max_consecutive_failures = 2
        for _ in range(4):
            s.run_cycle()
        self.assertFalse(s.workers[0].disabled)
        self.assertEqual(s.workers[0].consecutive_failures, 0)

    def test_emergency_stop_skips_only_order_placing_workers(self):
        ran = []
        s, _ = sup(
            [
                WorkerSpec("orders", lambda: ran.append("o"), places_orders=True),
                WorkerSpec("outbox", lambda: ran.append("x")),
            ],
            emergency=True,
        )
        result = s.run_cycle()
        self.assertEqual(result, {"orders": "SKIPPED_EMERGENCY_STOP", "outbox": "OK"})
        self.assertEqual(ran, ["x"])

    def test_run_respects_max_cycles_and_sleeps_between(self):
        s, sleeps = sup([WorkerSpec("w", lambda: None)])
        self.assertEqual(s.run(interval_seconds=2, max_cycles=3), 3)
        self.assertEqual(sleeps, [2, 2])

    def test_graceful_shutdown_finishes_current_cycle_then_stops(self):
        s = None
        order = []

        def worker():
            order.append("cycle")
            s.request_stop()  # stop requested mid-cycle

        s, sleeps = sup([WorkerSpec("w", worker)])
        cycles = s.run(interval_seconds=1)
        self.assertEqual(cycles, 1)
        self.assertEqual(order, ["cycle"])
        self.assertEqual(sleeps, [])  # no sleep after stop request
        self.assertTrue(s.stopping)


class MetricsTest(unittest.TestCase):
    def test_counters_and_gauges_render_prometheus_text(self):
        m = Metrics()
        m.inc("bangzen_worker_runs_total", worker="outbox")
        m.inc("bangzen_worker_runs_total", 2, worker="outbox")
        m.set_gauge("bangzen_supervisor_cycles", 7)
        text = m.render_prometheus()
        self.assertIn("# TYPE bangzen_worker_runs_total counter", text)
        self.assertIn('bangzen_worker_runs_total{worker="outbox"} 3', text)
        self.assertIn("bangzen_supervisor_cycles 7", text)

    def test_counter_cannot_decrease(self):
        with self.assertRaises(ValueError):
            Metrics().inc("x_total", -1)

    def test_invalid_metric_name_rejected(self):
        with self.assertRaises(ValueError):
            Metrics().inc("bad-name")

    def test_label_values_are_escaped(self):
        m = Metrics()
        m.inc("t_total", label='a"b\\c')
        self.assertIn('label="a\\"b\\\\c"', m.render_prometheus())


if __name__ == "__main__":
    unittest.main()
