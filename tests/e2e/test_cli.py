import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from bangzen_prime.interfaces.cli import main
from bangzen_prime.interfaces.demo import run_demo


def run_cli(argv, env=None):
    out, err = io.StringIO(), io.StringIO()
    with (
        mock.patch.dict(os.environ, env or {}, clear=True),
        contextlib.redirect_stdout(out),
        contextlib.redirect_stderr(err),
    ):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


class CliTest(unittest.TestCase):
    def test_help_exits_zero_and_lists_commands(self):
        with (
            self.assertRaises(SystemExit) as ctx,
            contextlib.redirect_stdout(io.StringIO()) as out,
        ):
            main(["--help"])
        self.assertEqual(ctx.exception.code, 0)
        text = out.getvalue()
        for command in ("status", "migrate", "scan", "outbox", "audit-verify", "demo"):
            self.assertIn(command, text)
        self.assertIn("locked", text)

    def test_status_reports_locked_defaults(self):
        code, out, _ = run_cli(["status"], {})
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertFalse(data["live_trading"])
        self.assertTrue(data["paper_trading"])
        self.assertTrue(data["dry_run"])
        self.assertNotIn(
            "token", json.dumps(data).lower().replace("telegram_configured", "")
        )

    def test_invalid_config_exits_nonzero_with_message(self):
        code, _, err = run_cli(["status"], {"BANGZEN_LIVE_TRADING": "true"})
        self.assertEqual(code, 1)
        self.assertIn("LIVE_TRADING is blocked", err)

    def test_audit_verify_on_fresh_file_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "a.db")
            code, out, _ = run_cli(["audit-verify"], {"BANGZEN_DB_PATH": path})
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(out)["intact"], True)

    def test_migrate_is_idempotent_from_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            env = {"BANGZEN_DB_PATH": os.path.join(tmp, "m.db")}
            _, first, _ = run_cli(["migrate"], env)
            _, second, _ = run_cli(["migrate"], env)
            self.assertEqual(json.loads(first)["schema_versions"], [1, 2, 3, 4, 5])
            self.assertEqual(json.loads(second)["schema_versions"], [1, 2, 3, 4, 5])

    def test_demo_runs_offline_end_to_end(self):
        code, out, _ = run_cli(["demo", "--scans", "25"])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertGreaterEqual(report["accepted_signals"], 0)
        self.assertEqual(report["ledger_mismatches"], [])
        self.assertIsNone(report["audit_chain_broken_at"])
        self.assertFalse(report["live_trading"])
        self.assertEqual(report["notifications_delivered"], report["accepted_signals"])

    def test_demo_report_function_matches_cli_contract(self):
        report = run_demo(scans=20)
        self.assertIn("paper_order", report)
        self.assertIsNone(report["audit_chain_broken_at"])


if __name__ == "__main__":
    unittest.main()
