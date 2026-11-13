import json
import unittest

from bangzen_prime.errors import ConfigurationError, ExternalServiceError
from bangzen_prime.infrastructure.adapters.messaging.telegram import (
    LABEL,
    MAX_MESSAGE_CHARS,
    TelegramNotifier,
    build_message,
    handle_command,
)
from bangzen_prime.infrastructure.http import HttpResponse, TransportTimeout
from bangzen_prime.infrastructure.resilience.policies import (
    CircuitBreaker,
    FakeClock,
    HealthMonitor,
    ResilientCaller,
    RetryPolicy,
    TokenBucket,
)
from tests.support import RecordingTransport

TOKEN = "123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
CHAT = "42"


def notifier(responses, *, clock=None, cooldown=60.0, sleeps=None):
    clock = clock or FakeClock()
    sleeps = sleeps if sleeps is not None else []
    queue = list(responses)

    def handler(url):
        item = queue.pop(0) if queue else HttpResponse(200, b'{"ok":true}', {})
        return item

    transport = RecordingTransport(handler)
    caller = ResilientCaller("telegram", retry=RetryPolicy(max_attempts=3, base_delay_seconds=0),
                             limiter=TokenBucket(rate_per_minute=6000, clock=clock),
                             breaker=CircuitBreaker("telegram", clock=clock), health=HealthMonitor(),
                             sleep=sleeps.append, clock=clock)
    n = TelegramNotifier(token=TOKEN, chat_id=CHAT, allowed_chat_ids=(CHAT,), transport=transport,
                         caller=caller, timeout=5, clock=clock.monotonic, cooldown_seconds=cooldown)
    return n, transport, sleeps, clock


class TelegramTest(unittest.TestCase):
    def test_send_success_uses_allowed_chat_and_labelled_html(self):
        n, transport, _, _ = notifier([])
        n.send("Entry 1.2 <b>x</b>")
        self.assertEqual(len(transport.calls), 1)
        url = transport.calls[0]
        self.assertIn("chat_id=42", url)
        self.assertIn("parse_mode=HTML", url)
        # user markup is escaped once: "<b>" -> "&lt;b&gt;" -> percent-encoded in the URL
        self.assertIn("%26lt%3Bb%26gt%3B", url)
        self.assertNotIn("%3Cb%3Ex", url)

    def test_html_escape_neutralises_markup(self):
        built = build_message("<script>alert(1)</script> & more")
        self.assertNotIn("<script>", built)
        self.assertIn("&lt;script&gt;", built)
        self.assertIn("&amp;", built)

    def test_label_always_present_and_not_duplicated(self):
        self.assertIn(LABEL, build_message("hello"))
        already = build_message(LABEL + " body")
        self.assertEqual(already.count(LABEL), 1)

    def test_long_message_is_capped(self):
        built = build_message("x" * 10_000)
        self.assertLessEqual(len(built), MAX_MESSAGE_CHARS)
        self.assertTrue(built.endswith("..."))

    def test_429_honours_retry_after_then_succeeds(self):
        body = json.dumps({"ok": False, "parameters": {"retry_after": 4}}).encode()
        n, transport, sleeps, _ = notifier([HttpResponse(429, body, {}), HttpResponse(200, b"{}", {})])
        n.send("hi")
        self.assertEqual(len(transport.calls), 2)
        self.assertEqual(sleeps, [4.0])

    def test_server_error_retries_then_fails_without_leaking_token(self):
        n, transport, _, _ = notifier([HttpResponse(500, b"", {})] * 5)
        with self.assertRaises(ExternalServiceError) as ctx:
            n.send("hi")
        self.assertNotIn(TOKEN, str(ctx.exception))
        self.assertNotIn("ABCDEFGHIJ", repr(ctx.exception))
        self.assertEqual(len(transport.calls), 3)

    def test_timeout_is_retryable(self):
        n, transport, _, _ = notifier([TransportTimeout()] * 5)
        with self.assertRaises(ExternalServiceError) as ctx:
            n.send("hi")
        self.assertTrue(ctx.exception.retryable)

    def test_400_not_retried(self):
        n, transport, _, _ = notifier([HttpResponse(400, b"", {})])
        with self.assertRaises(ExternalServiceError):
            n.send("hi")
        self.assertEqual(len(transport.calls), 1)

    def test_duplicate_within_cooldown_suppressed_then_allowed(self):
        n, transport, _, clock = notifier([], cooldown=60)
        n.send("same")
        n.send("same")
        self.assertEqual(len(transport.calls), 1)
        clock.advance(61)
        n.send("same")
        self.assertEqual(len(transport.calls), 2)

    def test_distinct_messages_not_suppressed(self):
        n, transport, _, _ = notifier([], cooldown=60)
        n.send("one")
        n.send("two")
        self.assertEqual(len(transport.calls), 2)

    def test_unauthorised_chat_rejected_at_construction(self):
        with self.assertRaises(ConfigurationError):
            TelegramNotifier(token=TOKEN, chat_id="99", allowed_chat_ids=("42",),
                             transport=lambda u, t: None, caller=None, timeout=1,
                             clock=lambda: 0.0)

    def test_missing_token_rejected(self):
        with self.assertRaises(ConfigurationError):
            TelegramNotifier(token="", chat_id="42", allowed_chat_ids=("42",),
                             transport=lambda u, t: None, caller=None, timeout=1,
                             clock=lambda: 0.0)

    def test_token_hidden_from_repr(self):
        n, _, _, _ = notifier([])
        self.assertNotIn("ABCDEFGHIJ", repr(n))


class CommandTest(unittest.TestCase):
    def test_status_reply_for_allowed_chat(self):
        out = handle_command(chat_id="42", command="/status now", allowed_chat_ids=("42",),
                             status_text=lambda: "live=false paper=true")
        self.assertIn("live=false", out)
        self.assertIn(LABEL, out)

    def test_unauthorised_chat_gets_no_reply(self):
        self.assertIsNone(handle_command(chat_id="7", command="/status", allowed_chat_ids=("42",),
                                         status_text=lambda: "secret"))

    def test_unknown_command_ignored(self):
        self.assertIsNone(handle_command(chat_id="42", command="/buy", allowed_chat_ids=("42",),
                                         status_text=lambda: "x"))
        self.assertIsNone(handle_command(chat_id="42", command="   ", allowed_chat_ids=("42",),
                                         status_text=lambda: "x"))


if __name__ == "__main__":
    unittest.main()
