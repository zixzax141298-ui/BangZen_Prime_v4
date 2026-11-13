import unittest
from datetime import UTC, datetime

from bangzen_prime.application.event_bus import EventBus
from bangzen_prime.domain.shared import DomainEvent
from bangzen_prime.errors import EventDispatchError

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class MemoryProcessed:
    def __init__(self):
        self.done = set()

    def is_processed(self, subscriber, event_id):
        return (subscriber, event_id) in self.done

    def mark_processed(self, subscriber, event_id, at):
        self.done.add((subscriber, event_id))


def event():
    return DomainEvent(name="E", payload={"k": 1}, occurred_at=NOW, event_id="evt-1")


class EventBusTest(unittest.TestCase):
    def test_partial_failure_still_runs_other_subscribers_and_raises_aggregate(self):
        ran = []
        bus = EventBus(MemoryProcessed(), lambda: NOW)
        bus.subscribe("E", "bad", lambda e: (_ for _ in ()).throw(RuntimeError("boom")))
        bus.subscribe("E", "good", lambda e: ran.append("good"))
        with self.assertRaises(EventDispatchError) as ctx:
            bus.dispatch(event())
        self.assertEqual(ran, ["good"])
        self.assertEqual([name for name, _ in ctx.exception.failures], ["bad"])

    def test_failed_subscriber_not_marked_processed_so_retry_runs_it(self):
        store = MemoryProcessed()
        bus = EventBus(store, lambda: NOW)
        attempts = []

        def flaky(e):
            attempts.append(1)
            if len(attempts) == 1:
                raise RuntimeError("first try fails")

        bus.subscribe("E", "flaky", flaky)
        with self.assertRaises(EventDispatchError):
            bus.dispatch(event())
        self.assertNotIn(("flaky", "evt-1"), store.done)
        bus.dispatch(event())
        self.assertEqual(len(attempts), 2)
        self.assertIn(("flaky", "evt-1"), store.done)

    def test_successful_subscriber_not_rerun_on_retry(self):
        store = MemoryProcessed()
        bus = EventBus(store, lambda: NOW)
        calls = {"ok": 0, "bad": 0}

        def ok(e):
            calls["ok"] += 1

        def bad(e):
            calls["bad"] += 1
            if calls["bad"] == 1:
                raise RuntimeError("retry me")

        bus.subscribe("E", "ok", ok)
        bus.subscribe("E", "bad", bad)
        with self.assertRaises(EventDispatchError):
            bus.dispatch(event())
        bus.dispatch(event())
        self.assertEqual(calls, {"ok": 1, "bad": 2})

    def test_duplicate_subscriber_name_rejected(self):
        bus = EventBus(MemoryProcessed(), lambda: NOW)
        bus.subscribe("E", "s", lambda e: None)
        with self.assertRaises(ValueError):
            bus.subscribe("E", "s", lambda e: None)

    def test_no_subscribers_is_a_noop(self):
        EventBus(MemoryProcessed(), lambda: NOW).dispatch(event())


if __name__ == "__main__":
    unittest.main()
