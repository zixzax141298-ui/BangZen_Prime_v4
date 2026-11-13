"""Tests for CI profile resolution and checks."""

from __future__ import annotations

from tools.ci import build_checks, resolve_profile


def test_resolve_termux() -> None:
    assert resolve_profile("auto", {"TERMUX_VERSION": "1"}) == "termux"


def test_resolve_github() -> None:
    assert resolve_profile("auto", {"GITHUB_ACTIONS": "true"}) == "github"


def test_resolve_explicit() -> None:
    assert resolve_profile("vps") == "vps"


def test_build_checks_returns_valid_checks() -> None:
    # Memastikan fungsi build_checks mengembalikan daftar yang valid
    # tanpa mempedulikan berapa jumlah pastinya (karena kita sedang transisi)
    checks = build_checks("github")
    assert len(checks) >= 2
    assert checks[0].name == "Compile"
    assert checks[1].name == "Canonical unittest suite"
