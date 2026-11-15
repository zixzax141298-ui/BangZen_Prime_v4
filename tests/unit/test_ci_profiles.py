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
        checks = build_checks("termux")

        applicable = [
            check.name for check in checks
            if "termux" in check.profiles and check.required
        ]

        self.assertEqual(
            applicable,
            ["Compile", "Canonical unittest suite"],
        )

    def test_github_profile_contains_mandatory_python_checks(self):
        checks = build_checks("github")
        required = {
            check.name for check in checks
            if check.required and "github" in check.profiles
        }

        self.assertTrue(
            {"Compile", "Canonical unittest suite"}.issubset(required)
        )

    def test_rust_checks_absent_when_manifest_missing(self):
        fake_manifest = Mock()
        fake_manifest.is_file.return_value = False

        with patch("tools.ci.RUST_MANIFEST", fake_manifest):
            names = {check.name for check in build_checks("vps")}

        self.assertNotIn("Cargo fmt", names)
        self.assertNotIn("Cargo test", names)

    def test_rust_checks_added_when_manifest_exists(self):
        fake_manifest = Mock()
        fake_manifest.is_file.return_value = True

        with patch("tools.ci.RUST_MANIFEST", fake_manifest):
            checks = build_checks("vps")

        rust_checks = {
            check.name: check
            for check in checks
            if check.name in {"Cargo fmt", "Cargo test"}
        }

        self.assertEqual(
            set(rust_checks),
            {"Cargo fmt", "Cargo test"},
        )

        for check in rust_checks.values():
            self.assertTrue(check.required)
            self.assertEqual(check.profiles, ("vps", "github"))

    def test_rust_checks_are_not_applicable_to_termux(self):
        checks = build_checks("termux")

        rust_checks = [
            check for check in checks
            if check.name in {"Cargo fmt", "Cargo test"}
        ]

        for check in rust_checks:
            self.assertNotIn("termux", check.profiles)


if __name__ == "__main__":
    unittest.main()
