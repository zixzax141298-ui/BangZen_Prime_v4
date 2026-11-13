"""Regression tests for portable CI profile selection."""

import unittest
from unittest.mock import Mock, patch

from tools.ci import build_checks, resolve_profile


class TestProfileResolution(unittest.TestCase):
    def test_auto_selects_termux(self):
        self.assertEqual(
            resolve_profile("auto", {"TERMUX_VERSION": "0.118"}),
            "termux",
        )

    def test_auto_selects_android_root(self):
        self.assertEqual(
            resolve_profile("auto", {"ANDROID_ROOT": "/system"}),
            "termux",
        )

    def test_auto_selects_github(self):
        self.assertEqual(
            resolve_profile("auto", {"GITHUB_ACTIONS": "true"}),
            "github",
        )

    def test_auto_defaults_to_vps(self):
        self.assertEqual(resolve_profile("auto", {}), "vps")

    def test_explicit_profile_wins(self):
        self.assertEqual(
            resolve_profile("termux", {"GITHUB_ACTIONS": "true"}),
            "termux",
        )

    def test_full_is_github_alias(self):
        self.assertEqual(resolve_profile("full", {}), "github")


class TestProfileChecks(unittest.TestCase):
    def test_termux_contains_only_portable_checks(self):
        names = [check.name for check in build_checks("termux")]
        self.assertEqual(
            names,
            ["Compile", "Canonical unittest suite"],
        )

    def test_full_profile_contains_python_security_checks(self):
        names = {check.name for check in build_checks("github")}
        required = {
            "Compile",
            "Canonical unittest suite",
            "Black",
            "Ruff",
            "Mypy",
            "Bandit",
            "Semgrep",
            "Pip-Audit",
        }
        self.assertTrue(required.issubset(names))

    def test_rust_checks_absent_when_manifest_missing(self):
        fake_manifest = Mock()
        fake_manifest.is_file.return_value = False
        with patch("tools.ci.RUST_MANIFEST", fake_manifest):
            names = {check.name for check in build_checks("vps")}
        self.assertNotIn("Cargo fmt", names)
        self.assertNotIn("Cargo test", names)
        self.assertNotIn("Cargo Audit", names)

    def test_rust_checks_added_when_manifest_exists(self):
        fake_manifest = Mock()
        fake_manifest.is_file.return_value = True
        with patch("tools.ci.RUST_MANIFEST", fake_manifest):
            names = {check.name for check in build_checks("vps")}
        self.assertTrue(
            {"Cargo fmt", "Cargo test", "Cargo Audit"}.issubset(names)
        )


if __name__ == "__main__":
    unittest.main()
