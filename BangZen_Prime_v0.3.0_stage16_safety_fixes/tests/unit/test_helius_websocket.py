"""Deterministic tests for the Helius WebSocket ingestion boundary."""

from __future__ import annotations

import unittest

from bangzen_prime.data.providers.helius_websocket import (
    HeliusLogEvent,
    HeliusStreamProtocolError,
    HeliusWebSocketConfig,
    build_logs_subscribe_request,
    parse_logs_notification,
)

ADDRESS = "11111111111111111111111111111111"


class HeliusWebSocketParserTests(unittest.TestCase):
    def test_builds_single_address_logs_subscription(self):
        request = build_logs_subscribe_request(ADDRESS)
        self.assertEqual(request["method"], "logsSubscribe")
        self.assertEqual(request["params"][0], {"mentions": [ADDRESS]})
        self.assertEqual(request["params"][1], {"commitment": "confirmed"})

    def test_rejects_invalid_address_and_commitment(self):
        with self.assertRaises(ValueError):
            build_logs_subscribe_request("not-a-solana-address")
        with self.assertRaises(ValueError):
            build_logs_subscribe_request(ADDRESS, "optimistic")

    def test_parses_valid_notification_without_inventing_fields(self):
        event = parse_logs_notification(
            {
                "jsonrpc": "2.0",
                "method": "logsNotification",
                "params": {
                    "result": {
                        "context": {"slot": 123},
                        "value": {
                            "signature": "sig-123",
                            "err": None,
                            "logs": ["Program log: instruction"],
                        },
                    }
                },
            }
        )
        self.assertEqual(
            event,
            HeliusLogEvent(
                slot=123,
                signature="sig-123",
                transaction_failed=False,
                logs=("Program log: instruction",),
            ),
        )

    def test_failed_transaction_is_preserved_as_failure_evidence(self):
        event = parse_logs_notification(
            {
                "method": "logsNotification",
                "params": {
                    "result": {
                        "context": {"slot": 1},
                        "value": {
                            "signature": "sig",
                            "err": {"InstructionError": [0, "x"]},
                            "logs": [],
                        },
                    }
                },
            }
        )
        self.assertTrue(event.transaction_failed)

    def test_unrelated_json_rpc_message_is_ignored(self):
        self.assertIsNone(
            parse_logs_notification({"jsonrpc": "2.0", "result": 7, "id": 1})
        )

    def test_malformed_notification_fails_closed(self):
        bad_payloads = [
            {"method": "logsNotification", "params": {}},
            {
                "method": "logsNotification",
                "params": {
                    "result": {
                        "context": {"slot": True},
                        "value": {"signature": "sig", "logs": []},
                    }
                },
            },
            {
                "method": "logsNotification",
                "params": {
                    "result": {
                        "context": {"slot": 1},
                        "value": {"signature": "sig", "logs": "not-a-list"},
                    }
                },
            },
        ]
        for payload in bad_payloads:
            with (
                self.subTest(payload=payload),
                self.assertRaises(HeliusStreamProtocolError),
            ):
                parse_logs_notification(payload)


class HeliusWebSocketConfigTests(unittest.TestCase):
    def test_api_key_is_not_exposed_in_config_repr(self):
        config = HeliusWebSocketConfig(api_key="super-secret-key")
        self.assertNotIn("super-secret-key", repr(config))

    def test_rejects_insecure_or_invalid_configuration(self):
        with self.assertRaises(ValueError):
            HeliusWebSocketConfig(api_key="key", endpoint="http://example.com")
        with self.assertRaises(ValueError):
            HeliusWebSocketConfig(api_key="key", max_reconnect_attempts=-1)


if __name__ == "__main__":
    unittest.main()
