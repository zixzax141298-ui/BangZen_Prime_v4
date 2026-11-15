import unittest
from decimal import Decimal

from bangzen_prime.core.config import Settings
from bangzen_prime.core.errors import ConfigurationError
from bangzen_prime.core.operating_mode import OperatingMode


class SettingsDefaultsTest(unittest.TestCase):
    def test_defaults_are_fail_safe(self):
        s = Settings()
        self.assertFalse(s.live_trading)
        self.assertTrue(s.paper_trading)
        self.assertTrue(s.dry_run)
        self.assertFalse(s.emergency_stop)
        self.assertEqual(s.operating_mode, OperatingMode.TELEGRAM_ONLY)

    def test_empty_env_gives_defaults(self):
        self.assertEqual(Settings.from_env({}), Settings())

    def test_optional_lunarcrush_key_is_loaded_and_hidden_from_repr(self):
        settings = Settings.from_env({"BANGZEN_LUNARCRUSH_API_KEY": "LUNAR-SECRET"})
        self.assertEqual(settings.lunarcrush_api_key, "LUNAR-SECRET")
        self.assertNotIn("LUNAR-SECRET", repr(settings))

    def test_token_is_not_shown_in_repr(self):
        s = Settings.from_env(
            {
                "BANGZEN_TELEGRAM_BOT_TOKEN": "123456:ABCDEFGHIJKLMNOPQRSTUVWXYZ012345",
                "BANGZEN_TELEGRAM_ALLOWED_CHAT_IDS": "12345",
            }
        )
        self.assertNotIn("ABCDEFGHIJKLMNOPQRSTUVWXYZ", repr(s))


class LiveLockTest(unittest.TestCase):
    def test_live_trading_true_rejected_from_env(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_LIVE_TRADING": "true"})

    def test_live_trading_true_rejected_on_direct_construction(self):
        with self.assertRaises(ConfigurationError):
            Settings(live_trading=True)

    def test_live_trading_rejected_even_when_provider_credentials_are_present(self):
        with self.assertRaisesRegex(
            ConfigurationError, "production execution pipeline is not implemented"
        ):
            Settings.from_env(
                {
                    "BANGZEN_LIVE_TRADING": "true",
                    "BANGZEN_HELIUS_API_KEY": "synthetic-test-key",
                }
            )

    def test_legacy_burner_private_key_setting_is_rejected(self):
        with self.assertRaisesRegex(
            ConfigurationError, "unknown configuration keys: BURNER_PRIVATE_KEY"
        ):
            Settings.from_env({"BANGZEN_BURNER_PRIVATE_KEY": "synthetic-test-key"})

    def test_paper_false_rejected(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_PAPER_TRADING": "false"})

    def test_dry_run_false_rejected(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_DRY_RUN": "0"})

    def test_operating_mode_accepts_all_supported_values(self):
        cases = {
            "TELEGRAM_ONLY": OperatingMode.TELEGRAM_ONLY,
            "EXECUTION_ONLY": OperatingMode.EXECUTION_ONLY,
            "HYBRID": OperatingMode.HYBRID,
        }
        for raw, expected in cases.items():
            with self.subTest(raw=raw):
                self.assertEqual(
                    Settings.from_env({"BANGZEN_OPERATING_MODE": raw}).operating_mode,
                    expected,
                )

    def test_operating_mode_is_case_insensitive_but_rejects_unknown_values(self):
        self.assertEqual(
            Settings.from_env({"BANGZEN_OPERATING_MODE": "hybrid"}).operating_mode,
            OperatingMode.HYBRID,
        )
        with self.assertRaisesRegex(ConfigurationError, "BANGZEN_OPERATING_MODE"):
            Settings.from_env({"BANGZEN_OPERATING_MODE": "LIVE"})

    def test_telegram_token_and_chat_allowlist_must_be_configured_together(self):
        with self.assertRaisesRegex(ConfigurationError, "configured together"):
            Settings.from_env({"BANGZEN_TELEGRAM_BOT_TOKEN": "synthetic-token"})
        with self.assertRaisesRegex(ConfigurationError, "configured together"):
            Settings.from_env({"BANGZEN_TELEGRAM_ALLOWED_CHAT_IDS": "12345"})

    def test_wallet_public_address_is_optional_and_validated(self):
        self.assertIsNone(Settings.from_env({}).wallet_public_address)
        settings = Settings.from_env(
            {
                "BANGZEN_WALLET_PUBLIC_ADDRESS": "So11111111111111111111111111111111111111112"
            }
        )
        self.assertEqual(
            settings.wallet_public_address,
            "So11111111111111111111111111111111111111112",
        )
        self.assertNotIn("So11111111111111111111111111111111111111112", repr(settings))

    def test_wallet_public_address_rejects_invalid_values(self):
        # Whitespace-only values are treated as unset (None) by the env parser.
        for address in ("not-a-solana-address", "0x1234", "invalid!!!"):
            with self.subTest(address=address), self.assertRaises(ConfigurationError):
                Settings.from_env({"BANGZEN_WALLET_PUBLIC_ADDRESS": address})

    def test_false_live_flag_is_accepted(self):
        self.assertFalse(
            Settings.from_env({"BANGZEN_LIVE_TRADING": "false"}).live_trading
        )


class ParsingTest(unittest.TestCase):
    def test_unknown_bangzen_key_is_rejected_to_catch_typos(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_LIVE_TRADNG": "false"})

    def test_non_bangzen_keys_are_ignored(self):
        self.assertEqual(Settings.from_env({"PATH": "/usr/bin"}), Settings())

    def test_legacy_owner_private_key_is_rejected_in_injected_environment(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"OWNER_PRIVATE_KEY": "must-not-be-loaded"})

    def test_invalid_boolean_rejected(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_EMERGENCY_STOP": "maybe"})

    def test_emergency_stop_can_be_enabled(self):
        self.assertTrue(
            Settings.from_env({"BANGZEN_EMERGENCY_STOP": "yes"}).emergency_stop
        )

    def test_nan_and_infinity_rejected(self):
        for raw in ("NaN", "Infinity", "-inf"):
            with self.subTest(raw=raw), self.assertRaises(ConfigurationError):
                Settings.from_env({"BANGZEN_MIN_LIQUIDITY_USD": raw})

    def test_non_numeric_decimal_rejected(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_FEE_RATE": "abc"})

    def test_fee_rate_boundaries(self):
        self.assertEqual(
            Settings.from_env({"BANGZEN_FEE_RATE": "0"}).fee_rate, Decimal(0)
        )
        self.assertEqual(
            Settings.from_env({"BANGZEN_FEE_RATE": "0.1"}).fee_rate, Decimal("0.1")
        )
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_FEE_RATE": "0.11"})

    def test_risk_percent_must_be_positive_and_at_most_100(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_MAX_RISK_PER_TRADE_PCT": "0"})
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_MAX_RISK_PER_TRADE_PCT": "100.5"})
        self.assertEqual(
            Settings.from_env(
                {"BANGZEN_MAX_RISK_PER_TRADE_PCT": "100"}
            ).max_risk_per_trade_pct,
            Decimal(100),
        )

    def test_http_urls_must_be_https(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env(
                {"BANGZEN_DEXSCREENER_BASE_URL": "http://api.example.com"}
            )

    def test_trailing_slash_removed_from_base_url(self):
        s = Settings.from_env(
            {"BANGZEN_RUGCHECK_BASE_URL": "https://api.example.com/v1/"}
        )
        self.assertEqual(s.rugcheck_base_url, "https://api.example.com/v1")

    def test_telegram_token_with_whitespace_rejected(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_TELEGRAM_BOT_TOKEN": "abc def"})

    def test_chat_ids_must_be_numeric(self):
        # Token and allowed chat ids must be configured together.
        with self.assertRaises(ConfigurationError):
            Settings.from_env(
                {
                    "BANGZEN_TELEGRAM_BOT_TOKEN": "123:ABC",
                    "BANGZEN_TELEGRAM_ALLOWED_CHAT_IDS": "12345,abc",
                }
            )
        s = Settings.from_env(
            {
                "BANGZEN_TELEGRAM_BOT_TOKEN": "123:ABC",
                "BANGZEN_TELEGRAM_ALLOWED_CHAT_IDS": "12345, -100987",
            }
        )
        self.assertEqual(s.telegram_allowed_chat_ids, ("12345", "-100987"))

    def test_invalid_log_level_rejected(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_LOG_LEVEL": "TRACE"})

    def test_integer_range_enforced(self):
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_HTTP_MAX_ATTEMPTS": "0"})
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_MAX_OPEN_POSITIONS": "two"})

    def test_env_example_keys_are_all_known_and_safe(self):
        import pathlib

        from bangzen_prime.core.config import Settings as S

        root = pathlib.Path(__file__).resolve().parents[2]
        values = {}
        for line in (root / ".env.example").read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key] = value
        self.assertTrue(values)
        settings = S.from_env(values)  # raises if any key is unknown or unsafe
        self.assertFalse(settings.live_trading)
        self.assertEqual(values["BANGZEN_TELEGRAM_BOT_TOKEN"], "")


if __name__ == "__main__":
    unittest.main()
