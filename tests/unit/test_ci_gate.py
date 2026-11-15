"""Regression tests for BANGZEN PRIME CI gate behavior."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from tools.ci import (
    ROOT,
    Check,
    build_report,
    evaluate_gate,
    main,
    run_check,
    write_report,
)


class TestRunCheck(unittest.TestCase):
    def test_successful_command_passes(self):
        check = Check(
            name="test",
            command=("python", "-c", "pass"),
        )

        with patch("tools.ci.subprocess.run") as mocked:
            mocked.return_value = Mock(returncode=0)
            result = run_check(check, 10, "termux")

        self.assertEqual(result["status"], "PASS")
        self.assertEqual(result["exit_code"], 0)

    def test_nonzero_exit_code_fails(self):
        check = Check(name="test", command=("false",))

        with patch("tools.ci.subprocess.run") as mocked:
            mocked.return_value = Mock(returncode=2)
            result = run_check(check, 10, "termux")

        self.assertEqual(result["status"], "FAIL")
        self.assertEqual(result["exit_code"], 2)

    def test_missing_required_path_is_blocked(self):
        check = Check(
            name="test",
            command=("python", "-c", "pass"),
            required_path="missing-ci-test-path",
        )

        with patch("tools.ci.subprocess.run") as mocked:
            result = run_check(check, 10, "termux")

        mocked.assert_not_called()
        self.assertEqual(result["status"], "BLOCKED")

    def test_missing_executable_is_blocked(self):
        check = Check(
            name="test",
            command=("missing-ci-executable",),
            executable="missing-ci-executable",
        )

        with patch("tools.ci.shutil.which", return_value=None):
            with patch("tools.ci.subprocess.run") as mocked:
                result = run_check(check, 10, "termux")

        mocked.assert_not_called()
        self.assertEqual(result["status"], "BLOCKED")

    def test_non_applicable_profile_is_not_run(self):
        check = Check(
            name="test",
            command=("python", "-c", "pass"),
            profiles=("github",),
        )

        with patch("tools.ci.subprocess.run") as mocked:
            result = run_check(check, 10, "termux")

        mocked.assert_not_called()
        self.assertEqual(result["status"], "NOT RUN")


class TestEvaluateGate(unittest.TestCase):
    def make_check(self, name="test", profiles=("github",), required=True):
        return Check(
            name=name,
            command=("python", "-c", "pass"),
            profiles=profiles,
            required=required,
        )

    def make_record(self, status="PASS"):
        return {"name": "test", "status": status}

    def test_github_gate_passes_only_when_required_checks_pass(self):
        checks = [self.make_check()]
        records = [self.make_record("PASS")]

        self.assertEqual(
            evaluate_gate("github", checks, records),
            ("GREEN", "FULL CI PASS", True),
        )

    def test_failed_check_fails_closed(self):
        checks = [self.make_check()]
        records = [self.make_record("FAIL")]

        self.assertEqual(
            evaluate_gate("github", checks, records),
            ("NOT GREEN", "FULL CI FAIL OR INCOMPLETE", False),
        )

    def test_blocked_check_fails_closed(self):
        checks = [self.make_check()]
        records = [self.make_record("BLOCKED")]

        self.assertEqual(
            evaluate_gate("github", checks, records)[2],
            False,
        )

    def test_not_run_required_check_fails_closed(self):
        checks = [self.make_check()]
        records = [self.make_record("NOT RUN")]

        self.assertEqual(
            evaluate_gate("github", checks, records)[2],
            False,
        )

    def test_termux_pass_is_not_full_ci_pass(self):
        checks = [self.make_check(profiles=("termux",))]
        records = [self.make_record("PASS")]

        self.assertEqual(
            evaluate_gate("termux", checks, records),
            ("LOCAL PASS", "FULL CI NOT RUN", True),
        )

    def test_no_required_checks_is_not_green(self):
        checks = [self.make_check(required=False)]
        records = [self.make_record("PASS")]

        self.assertEqual(
            evaluate_gate("github", checks, records),
            ("NOT GREEN", "NO REQUIRED CHECKS", False),
        )

    def test_mismatched_check_and_record_counts_raise(self):
        checks = [self.make_check()]
        records = []

        with self.assertRaises(ValueError):
            evaluate_gate("github", checks, records)

    def test_mismatched_check_and_record_names_raise(self):
        checks = [
            self.make_check(name="compile"),
            self.make_check(name="unit"),
        ]
        records = [
            {"name": "unit", "status": "PASS"},
            {"name": "compile", "status": "PASS"},
        ]

        with self.assertRaisesRegex(ValueError, "name mismatch"):
            evaluate_gate("github", checks, records)

    def test_missing_record_name_fails_closed(self):
        checks = [self.make_check(name="compile")]
        records = [{"status": "PASS"}]

        with self.assertRaisesRegex(ValueError, "name mismatch"):
            evaluate_gate("github", checks, records)


    def test_unknown_status_fails_closed(self):
        checks = [self.make_check()]
        records = [{"name": "test", "status": "UNKNOWN"}]

        with self.assertRaisesRegex(ValueError, "Unknown status"):
            evaluate_gate("github", checks, records)

    def test_unhashable_status_fails_closed(self):
        checks = [self.make_check()]
        records = [{"name": "test", "status": ["PASS"]}]

        with self.assertRaisesRegex(ValueError, "Unknown status"):
            evaluate_gate("github", checks, records)

    def test_dictionary_status_fails_closed(self):
        checks = [self.make_check()]
        records = [{"name": "test", "status": {"value": "PASS"}}]

        with self.assertRaisesRegex(ValueError, "Unknown status"):
            evaluate_gate("github", checks, records)

    def test_swapped_record_names_cannot_produce_green(self):
        checks = [
            self.make_check(name="compile"),
            self.make_check(name="unit"),
        ]
        records = [
            {"name": "unit", "status": "PASS"},
            {"name": "compile", "status": "PASS"},
        ]

        with self.assertRaisesRegex(ValueError, "name mismatch"):
            evaluate_gate("github", checks, records)


class TestBuildReport(unittest.TestCase):
    def test_report_counts_statuses(self):
        records = [
            {"status": "PASS"},
            {"status": "PASS"},
            {"status": "FAIL"},
            {"status": "BLOCKED"},
            {"status": "NOT RUN"},
        ]

        report = build_report(
            "github",
            "full",
            records,
            "NOT GREEN",
            "FULL CI FAIL OR INCOMPLETE",
        )

        self.assertEqual(
            report["counts"],
            {
                "PASS": 2,
                "FAIL": 1,
                "BLOCKED": 1,
                "NOT RUN": 1,
            },
        )
        self.assertEqual(report["resolved_profile"], "github")
        self.assertEqual(report["requested_profile"], "full")
        self.assertEqual(report["schema_version"], "1.1")


class TestWriteReport(unittest.TestCase):
    def test_report_is_written_as_valid_json(self):
        with tempfile.TemporaryDirectory(dir=ROOT) as temporary_directory:
            report_path = Path(temporary_directory).relative_to(ROOT) / "report.json"
            report = {"gate": "GREEN", "value": 123}

            result = write_report(str(report_path), report)

            self.assertIsNotNone(result)
            self.assertEqual(
                json.loads(result.read_text(encoding="utf-8")),
                report,
            )

    def test_empty_report_path_disables_writing(self):
        self.assertIsNone(write_report("", {"gate": "GREEN"}))

    def test_absolute_path_is_rejected(self):
        with self.assertRaises(ValueError):
            write_report("/tmp/ci-report.json", {})

    def test_path_traversal_is_rejected(self):
        with self.assertRaises(ValueError):
            write_report("../ci-report-outside.json", {})


class TestMain(unittest.TestCase):
    def test_successful_gate_returns_zero(self):
        with (
            patch("tools.ci.build_checks", return_value=[]),
            patch(
                "tools.ci.evaluate_gate",
                return_value=("LOCAL PASS", "FULL CI NOT RUN", True),
            ),
            patch(
                "tools.ci.build_report",
                return_value={
                    "counts": {
                        "PASS": 2,
                        "FAIL": 0,
                        "BLOCKED": 0,
                        "NOT RUN": 0,
                    }
                },
            ),
            patch("tools.ci.write_report", return_value=None),
        ):
            self.assertEqual(
                main(["--profile", "termux", "--report", ""]),
                0,
            )

    def test_failed_gate_returns_one(self):
        with (
            patch("tools.ci.build_checks", return_value=[]),
            patch(
                "tools.ci.evaluate_gate",
                return_value=("NOT GREEN", "FULL CI FAIL OR INCOMPLETE", False),
            ),
            patch(
                "tools.ci.build_report",
                return_value={
                    "counts": {
                        "PASS": 0,
                        "FAIL": 1,
                        "BLOCKED": 0,
                        "NOT RUN": 0,
                    }
                },
            ),
            patch("tools.ci.write_report", return_value=None),
        ):
            self.assertEqual(
                main(["--profile", "github", "--report", ""]),
                1,
            )

    def test_report_failure_returns_one(self):
        with (
            patch("tools.ci.build_checks", return_value=[]),
            patch(
                "tools.ci.evaluate_gate",
                return_value=("LOCAL PASS", "FULL CI NOT RUN", True),
            ),
            patch(
                "tools.ci.build_report",
                return_value={
                    "counts": {
                        "PASS": 0,
                        "FAIL": 0,
                        "BLOCKED": 0,
                        "NOT RUN": 0,
                    }
                },
            ),
            patch(
                "tools.ci.write_report",
                side_effect=OSError("simulated report failure"),
            ),
        ):
            self.assertEqual(
                main(["--profile", "termux"]),
                1,
            )


if __name__ == "__main__":
    unittest.main()
