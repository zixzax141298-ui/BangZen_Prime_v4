from __future__ import annotations

import unittest

from bangzen_prime.core.config import Settings
from bangzen_prime.core.errors import ConfigurationError
from bangzen_prime.core.operating_mode import OperatingMode, evaluate_mode
from bangzen_prime.core.state import ModeController


class OperatingModePolicyTest(unittest.TestCase):
    def test_telegram_only_never_allows_execution_or_wallet_access(self):
        state = evaluate_mode(
            OperatingMode.TELEGRAM_ONLY,
            kill_switch_engaged=False,
            live_execution_enabled=True,
        )
        self.assertTrue(state.telegram_enabled)
        self.assertFalse(state.execution_requested)
        self.assertFalse(state.execution_available)
        self.assertFalse(state.wallet_access_allowed)
        self.assertIn("EXECUTION_NOT_REQUESTED", state.reason_codes)

    def test_execution_only_has_no_telegram_and_is_still_locked_by_default(self):
        state = evaluate_mode(
            OperatingMode.EXECUTION_ONLY,
            kill_switch_engaged=True,
            live_execution_enabled=False,
        )
        self.assertFalse(state.telegram_enabled)
        self.assertTrue(state.execution_requested)
        self.assertFalse(state.execution_available)
        self.assertFalse(state.wallet_access_allowed)
        self.assertIn("EXECUTION_KILL_SWITCH_ENGAGED", state.reason_codes)
        self.assertIn("LIVE_EXECUTION_DISABLED_BY_POLICY", state.reason_codes)

    def test_hybrid_enables_telegram_but_does_not_bypass_execution_lock(self):
        state = evaluate_mode(
            OperatingMode.HYBRID,
            kill_switch_engaged=False,
            live_execution_enabled=False,
        )
        self.assertTrue(state.telegram_enabled)
        self.assertTrue(state.execution_requested)
        self.assertFalse(state.execution_available)
        self.assertFalse(state.wallet_access_allowed)

    def test_controller_defaults_to_telegram_only_and_locked(self):
        state = ModeController().snapshot()
        self.assertEqual(state.mode, OperatingMode.TELEGRAM_ONLY)
        self.assertTrue(state.telegram_enabled)
        self.assertTrue(state.kill_switch_engaged)
        self.assertFalse(state.wallet_access_allowed)

    def test_switching_to_telegram_only_latches_kill_switch(self):
        controller = ModeController()
        state = controller.select_mode(OperatingMode.TELEGRAM_ONLY)
        self.assertTrue(state.kill_switch_engaged)
        self.assertFalse(state.execution_available)

    def test_kill_switch_remains_engaged_after_selecting_execution_mode(self):
        controller = ModeController()
        controller.engage_kill_switch()
        state = controller.select_mode(OperatingMode.EXECUTION_ONLY)
        self.assertTrue(state.kill_switch_engaged)
        self.assertFalse(state.execution_available)

    def test_kill_switch_blocks_execution_assertion(self):
        controller = ModeController()
        controller.select_mode(OperatingMode.HYBRID)
        with self.assertRaises(PermissionError):
            controller.assert_execution_permitted()

    def test_invalid_mode_rejected(self):
        with self.assertRaises(TypeError):
            evaluate_mode("TELEGRAM_ONLY", kill_switch_engaged=True)  # type: ignore[arg-type]


class SettingsV3Test(unittest.TestCase):

    def test_live_trading_is_blocked(self):
        """LIVE_TRADING remains fail-closed until the full execution pipeline exists."""
        with self.assertRaises(ConfigurationError) as ctx:
            Settings.from_env(env={"BANGZEN_LIVE_TRADING": "true"})
        self.assertIn(
            "LIVE_TRADING is blocked: production execution pipeline is not implemented",
            str(ctx.exception),
        )

    def test_broadcast_requires_live_trading(self):
        with self.assertRaises(ConfigurationError) as ctx:
            Settings.from_env(env={"BANGZEN_BROADCAST_ENABLED": "true"})
        self.assertIn(
            "BROADCAST_ENABLED requires LIVE_TRADING=true", str(ctx.exception)
        )


if __name__ == "__main__":
    unittest.main()
