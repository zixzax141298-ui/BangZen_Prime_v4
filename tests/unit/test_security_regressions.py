"""Regression tests for the red-team findings. No network, no skips, no third-party imports.

Each class pins one finding so that it cannot silently come back.
Plaintext burner wallet and project-local ed25519 were removed (P6); those
surfaces are covered by test_removed_burner_wallet and test_burner_and_bundle.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import io
import os
import re
import shutil
import sqlite3
import sys
import tempfile
import types
import unittest
from unittest import mock

from bangzen_prime.errors import (
    ConfigurationError,
    DomainError,
    ExternalServiceError,
    PersistenceError,
)
from bangzen_prime.infrastructure.adapters.messaging.telegram import (
    MAX_MESSAGE_CHARS,
    build_message,
)
from bangzen_prime.infrastructure.http import (
    _OPENER,
    HttpResponse,
    _RefuseRedirects,
    get_json,
)
from bangzen_prime.infrastructure.persistence.sqlite import maintenance
from bangzen_prime.infrastructure.persistence.sqlite.database import Database
from bangzen_prime.settings import Settings

VALID_MINT = "So11111111111111111111111111111111111111112"
_DANGLING_ENTITY = re.compile(r"&(?!(amp|lt|gt);)")


class RedirectCredentialLeakTests(unittest.TestCase):
    def test_production_opener_refuses_redirects(self):
        self.assertTrue(any(isinstance(h, _RefuseRedirects) for h in _OPENER.handlers))
        handler = _RefuseRedirects()
        self.assertIsNone(
            handler.redirect_request(
                None, None, 302, "Found", {}, "http://evil.example/"
            )
        )

    def test_redirect_status_is_a_non_retryable_error(self):
        transport = lambda url, timeout: HttpResponse(
            302, b"", {"Location": "http://evil.example/"}
        )
        with self.assertRaises(ExternalServiceError) as ctx:
            get_json(
                service="rugcheck",
                url="https://api.rugcheck.xyz/v1/x",
                timeout=1,
                transport=transport,
            )
        self.assertFalse(ctx.exception.retryable)
        self.assertIn("redirect refused", str(ctx.exception))


class TelegramTruncationTests(unittest.TestCase):
    def test_truncation_never_leaves_a_dangling_entity(self):
        for text in ("&" * 3000, "a<b&c " * 1500, "x" * 10_000):
            with self.subTest(sample=text[:6]):
                msg = build_message(text)
                self.assertLessEqual(len(msg), MAX_MESSAGE_CHARS)
                self.assertIsNone(_DANGLING_ENTITY.search(msg))
                self.assertTrue(msg.endswith("..."))

    def test_short_message_is_untouched_except_label(self):
        self.assertIn("hello", build_message("hello"))


class ChatIdValidationTests(unittest.TestCase):
    def _settings(self, ids: str) -> Settings:
        return Settings.from_env(
            {
                "BANGZEN_TELEGRAM_BOT_TOKEN": "123:ABC",
                "BANGZEN_TELEGRAM_ALLOWED_CHAT_IDS": ids,
            }
        )

    def test_unicode_digits_are_rejected(self):
        # str.isdigit() accepts "²", so the old check let a non-numeric id through.
        self.assertTrue("²".isdigit())
        with self.assertRaises(ConfigurationError):
            self._settings("²")

    def test_ascii_ids_including_negative_groups_are_accepted(self):
        self.assertEqual(
            self._settings("12345,-100987").telegram_allowed_chat_ids,
            ("12345", "-100987"),
        )

    def test_mixed_garbage_is_rejected(self):
        for bad in ("12a", "--1", "1 2", "١٢٣"):
            with self.subTest(value=bad), self.assertRaises(ConfigurationError):
                self._settings(bad)


class ReadOnlyBackupVerificationTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._dir, ignore_errors=True)
        self.backup = os.path.join(self._dir, "backup.db")
        db = Database(self.backup)
        db.migrate()
        db.close()
        conn = sqlite3.connect(self.backup)
        conn.execute(
            "PRAGMA journal_mode=DELETE"
        )  # the form a copied backup normally has
        conn.close()

    def _digest(self, path: str) -> str:
        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    def test_verify_does_not_modify_the_backup_file(self):
        before = self._digest(self.backup)
        maintenance.verify_database_file(self.backup)
        self.assertEqual(self._digest(self.backup), before)

    def test_restore_leaves_source_backup_untouched(self):
        before = self._digest(self.backup)
        target = os.path.join(self._dir, "live.db")
        maintenance.restore(self.backup, target)
        self.assertEqual(self._digest(self.backup), before)
        maintenance.verify_database_file(target)

    def test_path_with_query_text_cannot_reenable_writes(self):
        crafted = os.path.join(self._dir, "x.db?mode=rw")
        shutil.copy(self.backup, crafted)
        conn = maintenance._open_readonly(crafted)
        try:
            with self.assertRaises(sqlite3.OperationalError):
                conn.execute("CREATE TABLE zz(a)")
        finally:
            conn.close()

    def test_non_database_file_is_reported_cleanly(self):
        junk = os.path.join(self._dir, "junk.db")
        with open(junk, "wb") as fh:
            fh.write(b"not a database" * 50)
        with self.assertRaises(PersistenceError):
            maintenance.verify_database_file(junk)


def _import_intel_cli():
    """Import intel_cli. httpx is optional and absent from CI, so use a stub for import only."""
    added = "httpx" not in sys.modules
    if added:
        sys.modules["httpx"] = types.ModuleType("httpx")
    try:
        from bangzen_prime.interfaces import intel_cli

        return intel_cli
    finally:
        if added:
            sys.modules.pop("httpx", None)


class IntelCliTests(unittest.TestCase):
    def setUp(self):
        self.ic = _import_intel_cli()
        self.ic._INTEL_CACHE.clear()
        self.addCleanup(self.ic._INTEL_CACHE.clear)

    def test_run_intel_rejects_injected_mint_before_any_io(self):
        injected = "../../admin?x=1"
        with self.assertRaises(DomainError):
            asyncio.run(self.ic.run_intel(injected))

    def test_cache_sources_do_not_clobber_each_other(self):
        # Before the fix, a trades entry without a "rugcheck" key made rugcheck raise KeyError.
        self.ic._cache_put("trades", VALID_MINT, [])
        self.assertIsNone(self.ic._cache_get("rugcheck", VALID_MINT))
        self.assertEqual(self.ic._cache_get("trades", VALID_MINT), [])

    def test_cached_rugcheck_result_is_returned_without_network(self):
        self.ic._cache_put("rugcheck", VALID_MINT, {"score": 42})
        with contextlib.redirect_stdout(io.StringIO()):
            result = asyncio.run(self.ic.fetch_rugcheck_raw(VALID_MINT))
        self.assertEqual(result, {"score": 42})


class DashboardOptionalDependencyTests(unittest.TestCase):
    def test_missing_dashboard_extra_gives_actionable_message(self):
        from bangzen_prime.interfaces import cli

        err = io.StringIO()
        # Setting a sys.modules entry to None makes the import raise ImportError deterministically.
        with (
            mock.patch.dict(sys.modules, {"bangzen_prime.interfaces.dashboard": None}),
            contextlib.redirect_stderr(err),
        ):
            code = cli.main(["dashboard"])
        self.assertEqual(code, cli.EXIT_ERROR)
        self.assertIn("bangzen-prime[dashboard]", err.getvalue())


class DotenvLoadingTests(unittest.TestCase):
    def setUp(self):
        from bangzen_prime.settings import load_settings_env, parse_env_file

        self.load_env, self.parse = load_settings_env, parse_env_file
        self._dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self._dir, ignore_errors=True)
        self.path = os.path.join(self._dir, ".env")

    def _write(self, text: str) -> None:
        with open(self.path, "w", encoding="utf-8") as fh:
            fh.write(text)

    def test_parses_bangzen_keys_and_ignores_comments_and_other_keys(self):
        self._write(
            '# c\nBANGZEN_LOG_LEVEL=WARNING\nexport BANGZEN_MAX_OPEN_POSITIONS="7"\n'
            "OTHER_SECRET=nope\n\n"
        )
        self.assertEqual(
            self.parse(self.path),
            {"BANGZEN_LOG_LEVEL": "WARNING", "BANGZEN_MAX_OPEN_POSITIONS": "7"},
        )

    def test_missing_file_means_no_overrides(self):
        self.assertEqual(self.parse(os.path.join(self._dir, "absent")), {})

    def test_real_environment_wins_over_file(self):
        self._write("BANGZEN_LOG_LEVEL=WARNING\n")
        with mock.patch.dict(os.environ, {"BANGZEN_LOG_LEVEL": "ERROR"}, clear=False):
            merged = self.load_env(self.path)
        self.assertEqual(merged["BANGZEN_LOG_LEVEL"], "ERROR")

    def test_file_values_are_validated_like_env_values(self):
        self._write("BANGZEN_LIVE_TRADING=true\n")
        with self.assertRaises(ConfigurationError):
            Settings.from_env(self.load_env(self.path))

    def test_non_bangzen_keys_in_file_are_not_loaded(self):
        self._write("OWNER_PRIVATE_KEY=abc\n")
        # Non-BANGZEN keys are not loaded, so the file itself cannot smuggle the key past the check.
        self.assertNotIn("OWNER_PRIVATE_KEY", self.load_env(self.path))
        with self.assertRaises(ConfigurationError):
            Settings.from_env({"OWNER_PRIVATE_KEY": "abc"})


class EmergencyStopTests(unittest.TestCase):
    def test_cli_refuses_signal_producing_commands_when_kill_switch_is_on(self):
        from bangzen_prime.interfaces import cli

        for command in (
            ["scan", "So11111111111111111111111111111111111111112"],
            ["discover", "--once"],
            ["outbox"],
        ):
            with self.subTest(command=command[0]):
                err = io.StringIO()
                with (
                    mock.patch.dict(os.environ, {"BANGZEN_EMERGENCY_STOP": "true"}),
                    mock.patch("bangzen_prime.bootstrap.build_container") as build,
                    contextlib.redirect_stderr(err),
                ):
                    code = cli.main(command)
                self.assertEqual(code, cli.EXIT_ERROR)
                self.assertIn("emergency stop is active", err.getvalue())
                build.assert_not_called()  # refused before any container or network is built

    def test_kill_switch_setting_reaches_settings(self):
        self.assertTrue(
            Settings.from_env({"BANGZEN_EMERGENCY_STOP": "true"}).emergency_stop
        )
        self.assertFalse(Settings.from_env({}).emergency_stop)


class LogRedactionTests(unittest.TestCase):
    def test_api_key_in_websocket_error_text_is_redacted(self):
        from bangzen_prime.logging_utils import redact

        msg = "[!] Error WebSocket: InvalidStatus wss://mainnet.helius-rpc.com/?api-key=SECRET123ABC"
        out = redact(msg)
        self.assertNotIn("SECRET123ABC", out)
        self.assertIn("<redacted>", out)


class DockerfileInvariantTests(unittest.TestCase):
    """Static checks: Docker is not available in the test environment."""

    def _dockerfile(self) -> str:
        here = os.path.dirname(os.path.abspath(__file__))
        with open(os.path.join(here, "..", "..", "Dockerfile"), encoding="utf-8") as fh:
            return fh.read()

    def test_rust_build_runs_where_cargo_toml_lives(self):
        # native/rust/Cargo.toml is the manifest; building from native/ fails.
        self.assertIn("WORKDIR /app/native/rust", self._dockerfile())

    def test_runtime_runs_as_non_root_user(self):
        text = self._dockerfile()
        self.assertIn("USER bangzen", text)
        self.assertNotIn("USER root", text)

    def test_package_is_installed_with_its_readme_present(self):
        # pyproject.toml declares readme = "README.md"; the install step must have it.
        text = self._dockerfile()
        self.assertIn("COPY . ./", text)
        self.assertLess(
            text.index("COPY . ./"), text.index("RUN pip install --no-cache-dir .")
        )


if __name__ == "__main__":
    unittest.main()
