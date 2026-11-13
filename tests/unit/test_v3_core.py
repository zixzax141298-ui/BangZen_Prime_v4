import unittest

from bangzen_prime.errors import ConfigurationError
from bangzen_prime.settings import Settings


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
