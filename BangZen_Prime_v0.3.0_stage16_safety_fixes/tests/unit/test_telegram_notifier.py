from __future__ import annotations

import json
import unittest

from bangzen_prime.core.errors import ExternalServiceError
from bangzen_prime.data.http import HttpResponse
from bangzen_prime.notifications.telegram import (
    TelegramNotifier,
)


class RecordingRequestTransport:
    def __init__(self, response: HttpResponse | None = None) -> None:
        self.calls = []
        self.response = response or HttpResponse(200, b'{"ok":true}', {})

    def __call__(self, request):
        self.calls.append(request)
        return self.response


class TelegramNotifierTest(unittest.TestCase):
    def test_sends_only_to_configured_allowlisted_chats(self):
        transport = RecordingRequestTransport()
        notifier = TelegramNotifier(
            token="12345:synthetic-token",
            chat_ids=("123", "-100456"),
            transport=transport,
            timeout=3.0,
        )

        notifier.send("Signal TEST")

        self.assertEqual(len(transport.calls), 2)
        payloads = [json.loads(call.body.decode("utf-8")) for call in transport.calls]
        self.assertEqual(
            [payload["chat_id"] for payload in payloads], ["123", "-100456"]
        )
        self.assertTrue(all(payload["text"] == "Signal TEST" for payload in payloads))
        self.assertTrue(all("parse_mode" not in payload for payload in payloads))
        self.assertTrue(all(call.method == "POST" for call in transport.calls))

    def test_token_is_redacted_from_repr_and_service_errors(self):
        token = "12345:synthetic-secret"
        transport = RecordingRequestTransport(HttpResponse(401, b'{"ok":false}', {}))
        notifier = TelegramNotifier(
            token=token,
            chat_ids=("123",),
            transport=transport,
            timeout=3.0,
        )

        self.assertNotIn(token, repr(notifier))
        with self.assertRaises(ExternalServiceError) as ctx:
            notifier.send("Signal")
        self.assertNotIn(token, str(ctx.exception))

    def test_rejects_empty_or_invalid_allowlist(self):
        transport = RecordingRequestTransport()
        for chat_ids in ((), ("abc",), ("123", "123")):
            with self.subTest(chat_ids=chat_ids), self.assertRaises(ValueError):
                TelegramNotifier(
                    token="12345:synthetic-token",
                    chat_ids=chat_ids,
                    transport=transport,
                    timeout=3.0,
                )

    def test_rejects_empty_or_oversized_messages(self):
        notifier = TelegramNotifier(
            token="12345:synthetic-token",
            chat_ids=("123",),
            transport=RecordingRequestTransport(),
            timeout=3.0,
        )
        with self.assertRaises(ValueError):
            notifier.send(" ")
        with self.assertRaises(ValueError):
            notifier.send("x" * 4097)

    def test_transport_exception_is_sanitized(self):
        token = "12345:synthetic-secret"

        def fail_with_request_url(request):
            raise RuntimeError(request.url)

        notifier = TelegramNotifier(
            token=token,
            chat_ids=("123",),
            transport=fail_with_request_url,
            timeout=3.0,
        )
        with self.assertRaises(ExternalServiceError) as ctx:
            notifier.send("Signal")
        self.assertNotIn(token, str(ctx.exception))
        self.assertEqual(str(ctx.exception), "telegram transport failed")

    def test_rejects_string_allowlist_and_non_finite_timeout(self):
        transport = RecordingRequestTransport()
        with self.assertRaises(ValueError):
            TelegramNotifier(
                token="12345:synthetic-token",
                chat_ids="12345",
                transport=transport,
                timeout=3.0,
            )
        for timeout in (0, float("nan"), float("inf"), True):
            with self.subTest(timeout=timeout), self.assertRaises(ValueError):
                TelegramNotifier(
                    token="12345:synthetic-token",
                    chat_ids=("123",),
                    transport=transport,
                    timeout=timeout,
                )


if __name__ == "__main__":
    unittest.main()
