import io
import json
import logging
import unittest

from bangzen_prime.logging_utils import RedactionFilter, configure_logging, redact


class RedactionTest(unittest.TestCase):
    def test_telegram_token_is_masked(self):
        text = "sending with 123456789:ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 now"
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZ", redact(text))
        self.assertIn("<redacted-telegram-token>", redact(text))

    def test_key_value_secrets_are_masked(self):
        self.assertEqual(redact("api_key=abc123 ok"), "api_key=<redacted> ok")
        self.assertEqual(redact("password: hunter2,"), "password: <redacted>,")

    def test_plain_text_untouched(self):
        self.assertEqual(redact("entry 0.001 liquidity 10000"), "entry 0.001 liquidity 10000")

    def test_json_logger_never_emits_secret(self):
        stream = io.StringIO()
        logger = configure_logging("INFO", stream)
        logger.info("token=supersecretvalue ok")
        line = stream.getvalue().strip()
        record = json.loads(line)
        self.assertEqual(record["level"], "INFO")
        self.assertNotIn("supersecretvalue", line)

    def test_filter_clears_args(self):
        record = logging.LogRecord("x", logging.INFO, __file__, 1, "value %s", ("secret=abc",), None)
        self.assertTrue(RedactionFilter().filter(record))
        self.assertEqual(record.args, ())
        self.assertNotIn("abc", record.msg)


if __name__ == "__main__":
    unittest.main()
