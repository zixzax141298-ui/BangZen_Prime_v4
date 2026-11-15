"""Regression tests for the four safety fixes:
1. HALT.flag and .env resolve to absolute paths (working directory cannot hide the kill switch).
2. Continuous discovery checks the emergency stop before every scan batch.
3. Secrets in error text are redacted, including Bearer tokens and x-api-key headers.
4. WalletSigner exposes the call-site method `sign` and always refuses.
"""

import os
import tempfile
import unittest

from bangzen_prime.core.config import Settings
from bangzen_prime.core.errors import ConfigurationError, HaltEngagedError
from bangzen_prime.core.interfaces.cli import resolve_env_file
from bangzen_prime.core.logging_utils import redact
from bangzen_prime.discovery.scanner import ContinuousDiscoveryUseCase
from bangzen_prime.execution.signing import SigningDisabled
from bangzen_prime.execution.wallet_signer import WalletSigner
from bangzen_prime.risk.emergency_stop import halt_engaged, halt_flag_engaged

MINT = "So11111111111111111111111111111111111111112"


class HaltPathTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self._cwd = os.getcwd()
        self.addCleanup(os.chdir, self._cwd)

    def test_default_halt_path_is_absolute(self):
        self.assertTrue(os.path.isabs(Settings().halt_flag_path))

    def test_relative_halt_path_is_refused(self):
        with self.assertRaises(ConfigurationError):
            Settings(halt_flag_path="HALT.flag")

    def test_halt_path_from_env_is_honoured_and_checked(self):
        abs_path = os.path.join(self._tmp.name, "HALT.flag")
        s = Settings.from_env({"BANGZEN_HALT_FLAG_PATH": abs_path})
        self.assertEqual(s.halt_flag_path, abs_path)
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"BANGZEN_HALT_FLAG_PATH": "relative/HALT.flag"})

    def test_kill_switch_is_seen_from_any_working_directory(self):
        flag = os.path.join(self._tmp.name, "HALT.flag")
        open(flag, "w").close()
        other = tempfile.mkdtemp()
        self.addCleanup(os.rmdir, other)
        os.chdir(other)
        self.assertTrue(Settings(halt_flag_path=flag).halt_active())
        self.assertTrue(halt_engaged(False, flag))

    def test_missing_flag_does_not_halt_and_unreadable_path_fails_closed(self):
        absent = os.path.join(self._tmp.name, "HALT.flag")
        self.assertFalse(halt_flag_engaged(absent))
        blocker = os.path.join(self._tmp.name, "file")
        open(blocker, "w").close()
        # The parent is a regular file, so the stat error is not "not found": fail closed.
        self.assertTrue(halt_flag_engaged(os.path.join(blocker, "HALT.flag")))

    def test_env_var_kill_switch_still_halts(self):
        self.assertTrue(Settings(emergency_stop=True, halt_flag_path=os.path.join(self._tmp.name, "x")).halt_active())

    def test_explicit_missing_env_file_is_an_error(self):
        with self.assertRaises(ConfigurationError):
            resolve_env_file({"BANGZEN_ENV_FILE": os.path.join(self._tmp.name, "nope.env")})

    def test_default_env_file_is_dot_env_when_unset(self):
        self.assertEqual(resolve_env_file({}), ".env")


class _Feed:
    def __init__(self):
        self.calls = 0

    def fetch_candidates(self, *, limit):
        self.calls += 1
        return [MINT]


class _Scanner:
    def __init__(self):
        self.calls = 0

    def execute(self, chain, mints):
        self.calls += 1
        return []


class DiscoveryHaltTests(unittest.TestCase):
    def test_halted_before_cycle_starts_nothing_runs(self):
        feed, scanner = _Feed(), _Scanner()
        uc = ContinuousDiscoveryUseCase(feed=feed, scanner=scanner, halt_check=lambda: True)
        with self.assertRaises(HaltEngagedError):
            uc.execute(limit=5)
        self.assertEqual((feed.calls, scanner.calls), (0, 0))

    def test_halt_engaged_mid_cycle_stops_before_scanning(self):
        feed, scanner = _Feed(), _Scanner()
        answers = iter([False, True])
        uc = ContinuousDiscoveryUseCase(
            feed=feed, scanner=scanner, halt_check=lambda: next(answers)
        )
        with self.assertRaises(HaltEngagedError):
            uc.execute(limit=5)
        self.assertEqual(feed.calls, 1)
        self.assertEqual(scanner.calls, 0)

    def test_no_halt_check_keeps_normal_behaviour(self):
        feed, scanner = _Feed(), _Scanner()
        ContinuousDiscoveryUseCase(feed=feed, scanner=scanner).execute(limit=5)
        self.assertEqual((feed.calls, scanner.calls), (1, 1))


class RedactionTests(unittest.TestCase):
    def test_query_string_api_key_is_removed(self):
        text = "error at https://mainnet.helius-rpc.com/?api-key=SECRETVALUE123&x=1"
        self.assertNotIn("SECRETVALUE123", redact(text))

    def test_bearer_token_is_removed(self):
        self.assertNotIn("BEARERSECRET", redact("Authorization: Bearer BEARERSECRET"))

    def test_x_api_key_header_is_removed(self):
        self.assertNotIn("HEADERSECRET", redact("x-api-key: HEADERSECRET"))

    def test_telegram_token_in_url_is_removed(self):
        token = "123456789:" + "A" * 35
        self.assertNotIn(token, redact(f"https://api.telegram.org/bot{token}/sendMessage"))

    def test_ordinary_text_is_untouched(self):
        self.assertEqual(redact("discovery halted: emergency stop engaged"), "discovery halted: emergency stop engaged")


class WalletSignerTests(unittest.TestCase):
    def _instance(self):
        # Bypass __init__, which always refuses. Only the method contract is tested here.
        return object.__new__(WalletSigner)

    def test_sign_matches_call_site_and_refuses(self):
        self.assertTrue(callable(getattr(WalletSigner, "sign", None)))
        with self.assertRaises(SigningDisabled):
            self._instance().sign(object())

    def test_legacy_sign_transaction_still_refuses(self):
        with self.assertRaises(SigningDisabled):
            self._instance().sign_transaction("AAAA")

    def test_constructor_refuses(self):
        with self.assertRaises(SigningDisabled):
            WalletSigner("ignored")


class SystemdUnitTests(unittest.TestCase):
    UNITS = (
        "bangzen-prime-monitor.service",
        "bangzen-prime-discover.service",
        "bangzen-prime-daily-report.service",
    )

    def test_every_service_pins_env_file_and_halt_flag_to_absolute_paths(self):
        root = os.path.join(os.path.dirname(__file__), "..", "..", "deploy", "systemd")
        for unit in self.UNITS:
            with self.subTest(unit=unit):
                text = open(os.path.join(root, unit), encoding="utf-8").read()
                self.assertIn("Environment=BANGZEN_ENV_FILE=__APP_DIR__/.env", text)
                self.assertIn("Environment=BANGZEN_HALT_FLAG_PATH=__APP_DIR__/HALT.flag", text)


if __name__ == "__main__":
    unittest.main()
