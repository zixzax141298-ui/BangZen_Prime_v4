from __future__ import annotations

import unittest

from bangzen_prime.core.operating_mode import OperatingMode
from bangzen_prime.core.state import ModeController
from bangzen_prime.execution.wallet_access import (
    WalletAccessController,
    WalletAccessDenied,
    WalletRegistry,
)

PUBLIC_ADDRESS = "So11111111111111111111111111111111111111112"


class WatchOnlyWalletRegistryTest(unittest.TestCase):
    def test_registry_stores_only_public_address(self):
        registry = WalletRegistry(PUBLIC_ADDRESS)
        self.assertTrue(registry.configured)
        self.assertEqual(registry.public_address, PUBLIC_ADDRESS)
        self.assertNotIn("private", repr(registry).lower())
        self.assertNotIn("seed", repr(registry).lower())
        self.assertNotIn(PUBLIC_ADDRESS, repr(registry))

    def test_registry_rejects_invalid_public_address(self):
        with self.assertRaisesRegex(ValueError, "valid Solana public address"):
            WalletRegistry("not-a-wallet")

    def test_missing_address_is_a_closed_watch_only_state(self):
        controller = WalletAccessController(
            registry=WalletRegistry(),
            mode_controller=ModeController(OperatingMode.TELEGRAM_ONLY),
            emergency_stop=False,
        )
        snapshot = controller.snapshot()
        self.assertFalse(snapshot.public_address_configured)
        self.assertFalse(snapshot.signer_available)
        self.assertFalse(snapshot.funds_usable)
        self.assertIn("WALLET_PUBLIC_ADDRESS_NOT_CONFIGURED", snapshot.reason_codes)
        self.assertIn("SIGNER_UNAVAILABLE", snapshot.reason_codes)

    def test_execution_requested_does_not_grant_signer_or_fund_access(self):
        controller = WalletAccessController(
            registry=WalletRegistry(PUBLIC_ADDRESS),
            mode_controller=ModeController(OperatingMode.HYBRID),
            emergency_stop=False,
        )
        snapshot = controller.snapshot()
        self.assertEqual(snapshot.mode, OperatingMode.HYBRID)
        self.assertTrue(snapshot.public_address_configured)
        self.assertEqual(snapshot.public_address, PUBLIC_ADDRESS)
        self.assertFalse(snapshot.signer_available)
        self.assertFalse(snapshot.funds_usable)
        self.assertIn("LIVE_EXECUTION_DISABLED_BY_POLICY", snapshot.reason_codes)
        self.assertNotIn(PUBLIC_ADDRESS, repr(snapshot))

    def test_emergency_stop_is_reported_and_access_is_denied(self):
        controller = WalletAccessController(
            registry=WalletRegistry(PUBLIC_ADDRESS),
            mode_controller=ModeController(OperatingMode.EXECUTION_ONLY),
            emergency_stop=True,
        )
        snapshot = controller.snapshot()
        self.assertTrue(snapshot.emergency_stop_engaged)
        self.assertIn("EMERGENCY_STOP_ENGAGED", snapshot.reason_codes)
        with self.assertRaises(WalletAccessDenied):
            controller.assert_signer_access()
        with self.assertRaises(WalletAccessDenied):
            controller.assert_funds_usable()

    def test_no_mode_can_unlock_signer_access(self):
        for mode in OperatingMode:
            with self.subTest(mode=mode):
                controller = WalletAccessController(
                    registry=WalletRegistry(PUBLIC_ADDRESS),
                    mode_controller=ModeController(mode),
                    emergency_stop=False,
                )
                self.assertFalse(controller.snapshot().signer_available)
                self.assertFalse(controller.snapshot().funds_usable)
                with self.assertRaises(WalletAccessDenied):
                    controller.assert_signer_access()


if __name__ == "__main__":
    unittest.main()
