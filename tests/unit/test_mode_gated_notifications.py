from __future__ import annotations

import unittest

from bangzen_prime.application.mode_controller import ModeController
from bangzen_prime.application.notifications import ModeGatedNotifier
from bangzen_prime.domain.operating_mode import OperatingMode


class RecordingNotifier:
    def __init__(self) -> None:
        self.messages: list[str] = []

    def send(self, text: str) -> None:
        self.messages.append(text)


class ModeGatedNotifierTest(unittest.TestCase):
    def test_telegram_only_delivers_signal(self):
        target = RecordingNotifier()
        gate = ModeGatedNotifier(target, ModeController(OperatingMode.TELEGRAM_ONLY))
        gate.send("signal")
        self.assertEqual(target.messages, ["signal"])

    def test_execution_only_suppresses_telegram_delivery(self):
        target = RecordingNotifier()
        gate = ModeGatedNotifier(target, ModeController(OperatingMode.EXECUTION_ONLY))
        gate.send("signal")
        self.assertEqual(target.messages, [])

    def test_hybrid_delivers_telegram_but_does_not_unlock_wallet(self):
        controller = ModeController(OperatingMode.HYBRID)
        target = RecordingNotifier()
        ModeGatedNotifier(target, controller).send("signal")
        self.assertEqual(target.messages, ["signal"])
        self.assertFalse(controller.snapshot().wallet_access_allowed)
        self.assertFalse(controller.snapshot().execution_available)


if __name__ == "__main__":
    unittest.main()
