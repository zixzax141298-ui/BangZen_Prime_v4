"""Portable, fail-closed validation gate for BANGZEN PRIME."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
FULL_PROFILES = ("vps", "github")
ALL_PROFILES = ("termux", *FULL_PROFILES)

PYTHON_PATHS = tuple(
    path
    for path in ("bangzen_prime", "tests", "scripts", "tools")
    if (ROOT / path).exists()
)

RUST_MANIFEST = ROOT / "native" / "rust" / "Cargo.toml"


@dataclass(frozen=True)
class Check:
    name: str
    command: tuple[str, ...]
    executable: str | None = None
    required: bool = True
    required_path: str | None = None
    profiles: tuple[str, ...] = FULL_PROFILES


def resolve_profile(
    requested: str,
    environ: dict[str, str] | None = None,
) -> str:
    """Resolve the execution profile without assuming a Linux distribution."""
    env = os.environ if environ is None else environ

    if requested != "auto":
        return "github" if requested == "full" else requested

    if env.get("TERMUX_VERSION") or env.get("ANDROID_ROOT"):
        return "termux"

    if env.get("GITHUB_ACTIONS", "").lower() == "true":
        return "github"

    return "vps"


def python_checks() -> list[Check]:
    """Return Python checks, separating portable tests from full CI tools."""
    checks = [
        Check(
            name="Compile",
            command=(
                sys.executable,
                "-m",
                "compileall",
                "-q",
                *PYTHON_PATHS,
            ),
            profiles=ALL_PROFILES,
        ),
        Check(
            name="Canonical unittest suite",
            command=(sys.executable, "scripts/run_tests.py"),
            required_path="scripts/run_tests.py",
            profiles=ALL_PROFILES,
        ),
    ]

    if PYTHON_PATHS:
        checks.extend(
            [
                Check(
                    name="Black",
                    command=(
                        sys.executable,
                        "-m",
                        "black",
                        "--check",
                        *PYTHON_PATHS,
                    ),
                ),
                Check(
                    name="Ruff",
                    command=(
                        sys.executable,
                        "-m",
                        "ruff",
                        "check",
                        *PYTHON_PATHS,
                    ),
                ),
                Check(
                    name="Mypy",
                    command=(
                        sys.executable,
                        "-m",
                        "mypy",
                        "bangzen_prime",
                    ),
                    required_path="bangzen_prime",
                ),
                Check(
                    name="Bandit",
                    command=(
                        sys.executable,
                        "-m",
                        "bandit",
                        "-q",
                        "-r",
                        "bangzen_prime",
                    ),
                    required_path="bangzen_prime",
                ),
                Check(
                    name="Semgrep",
                    command=(
                        "semgrep",
                        "scan",
                        "--config",
                        "auto",
                        "--error",
                        "bangzen_prime",
                    ),
                    executable="semgrep",
                    required_path="bangzen_prime",
                ),
                Check(
                    name="Pip-Audit",
                    command=(
                        "pip-audit",
                        "--strict",
                        "--skip-editable",
                    ),
                    executable="pip-audit",
                ),
            ]
        )

    return checks


def build_checks(profile: str) -> list[Check]:
    """Build the complete check inventory for the selected profile."""
    checks = python_checks()

    if RUST_MANIFEST.is_file():
        checks.extend(
            [
                Check(
                    name="Cargo fmt",
                    command=(
                        "cargo",
                        "fmt",
                        "--manifest-path",
                        "native/rust/Cargo.toml",
                        "--",
                        "--check",
                    ),
                    executable="cargo",
                ),
                Check(
                    name="Cargo test",
                    command=(
                        "cargo",
                        "test",
                        "--manifest-path",
                        "native/rust/Cargo.toml",
                    ),
                    executable="cargo",
                ),
                Check(
                    name="Cargo Audit",
                    command=(
                        "cargo",
                        "audit",
                        "--file",
                        "native/rust/Cargo.lock",
                    ),
                    executable="cargo",
                    required_path="native/rust/Cargo.lock",
                ),
            ]
        )

    # Keep the profile argument explicit. Checks outside the selected
    # profile remain visible in the report as NOT RUN.
    if profile not in ALL_PROFILES:
        raise ValueError(f"Unsupported profile: {profile}")

    return checks


def skipped_record(check: Check, profile: str) -> dict[str, Any]:
    return {
        "name": check.name,
        "command": list(check.command),
        "required": check.required,
        "status": "NOT RUN",
        "exit_code": None,
        "duration_seconds": 0.0,
        "detail": f"Not included in the {profile} profile",
    }


def run_check(check: Check, timeout: int, profile: str) -> dict[str, Any]:
    """Run one check and return a machine-readable result."""
    if profile not in check.profiles:
        return skipped_record(check, profile)

    started = time.monotonic()

    record: dict[str, Any] = {
        "name": check.name,
        "command": list(check.command),
        "required": check.required,
        "status": "",
        "exit_code": None,
        "duration_seconds": 0.0,
        "detail": "",
    }

    if check.required_path:
        required_path = ROOT / check.required_path
        if not required_path.exists():
            record.update(
                status="BLOCKED",
                detail=f"Required path missing: {check.required_path}",
            )
            return record

    if check.executable and shutil.which(check.executable) is None:
        record.update(
            status="BLOCKED" if check.required else "NOT RUN",
            detail=f"Executable unavailable: {check.executable}",
        )
        return record

    print(f"\n=== {check.name} ===", flush=True)
    print("$ " + " ".join(check.command), flush=True)

    try:
        completed = subprocess.run(
            check.command,
            cwd=ROOT,
            check=False,
            timeout=timeout,
            text=True,
        )
        record["exit_code"] = completed.returncode
        record["status"] = (
            "PASS" if completed.returncode == 0 else "FAIL"
        )
        record["detail"] = (
            "Command completed"
            if completed.returncode == 0
            else f"Exit code {completed.returncode}"
        )

    except FileNotFoundError:
        record.update(
            status="BLOCKED",
            detail="Executable could not be started",
        )

    except subprocess.TimeoutExpired:
        record.update(
            status="FAIL",
            detail=f"Timed out after {timeout}s",
        )

    except OSError as exc:
        record.update(
            status="FAIL",
            detail=f"Execution error: {type(exc).__name__}",
        )

    record["duration_seconds"] = round(
        time.monotonic() - started,
        3,
    )

    print(
        f"{record['status']}: {check.name} — {record['detail']}",
        flush=True,
    )

    return record


def evaluate_gate(
    profile: str,
    checks: list[Check],
    records: list[dict[str, Any]],
) -> tuple[str, str, bool]:
    """Evaluate only applicable required checks; never treat NOT RUN as PASS."""
    applicable = [
        (check, record)
        for check, record in zip(checks, records, strict=True)
        if profile in check.profiles and check.required
    ]

    if not applicable:
        return "NOT GREEN", "NO REQUIRED CHECKS", False

    all_passed = all(
        record["status"] == "PASS"
        for _, record in applicable
    )

    if profile == "termux":
        if all_passed:
            return "LOCAL PASS", "FULL CI NOT RUN", True
        return "LOCAL FAIL", "FULL CI NOT RUN", False

    if all_passed:
        return "GREEN", "FULL CI PASS", True

    return "NOT GREEN", "FULL CI FAIL OR INCOMPLETE", False


def build_report(
    profile: str,
    requested_profile: str,
    records: list[dict[str, Any]],
    gate: str,
    full_ci_status: str,
) -> dict[str, Any]:
    statuses = ("PASS", "FAIL", "BLOCKED", "NOT RUN")
    counts = {
        status: sum(record["status"] == status for record in records)
        for status in statuses
    }

    return {
        "schema_version": "1.1",
        "project": "BANGZEN PRIME",
        "created_at": datetime.now(UTC).isoformat(),
        "requested_profile": requested_profile,
        "resolved_profile": profile,
        "python": sys.version.split()[0],
        "platform": platform.platform(),
        "repository_root": str(ROOT),
        "counts": counts,
        "checks": records,
        "gate": gate,
        "full_ci_status": full_ci_status,
    }


def write_report(report_path: str, report: dict[str, Any]) -> Path | None:
    """Write the report atomically and only inside the repository."""
    if not report_path:
        return None

    requested = Path(report_path)

    if requested.is_absolute():
        raise ValueError("Report path must be relative to the repository")

    target = (ROOT / requested).resolve()
    root_resolved = ROOT.resolve()

    if not target.is_relative_to(root_resolved):
        raise ValueError("Report path must remain inside the repository")

    target.parent.mkdir(parents=True, exist_ok=True)

    temporary_path: Path | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=target.parent,
            prefix=f".{target.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(report, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())

        os.replace(temporary_path, target)
        return target

    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="BANGZEN PRIME portable CI gate"
    )
    parser.add_argument(
        "--profile",
        choices=("auto", "termux", "vps", "github", "full"),
        default="auto",
    )
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument(
        "--report",
        default="reports/ci-report.json",
        help="JSON report path; empty disables report",
    )

    args = parser.parse_args(argv)

    if args.timeout < 1:
        parser.error("--timeout must be positive")

    profile = resolve_profile(args.profile)

    try:
        checks = build_checks(profile)
    except ValueError as exc:
        parser.error(str(exc))

    print(
        "BANGZEN PRIME CI | "
        f"profile={profile} | "
        f"Python={sys.version.split()[0]} | "
        f"{platform.platform()}",
        flush=True,
    )

    records = [
        run_check(check, args.timeout, profile)
        for check in checks
    ]

    gate, full_ci_status, successful = evaluate_gate(
        profile,
        checks,
        records,
    )

    report = build_report(
        profile,
        args.profile,
        records,
        gate,
        full_ci_status,
    )

    try:
        report_file = write_report(args.report, report)
    except (OSError, ValueError) as exc:
        print(
            f"\nREPORT FAILURE: {type(exc).__name__}: {exc}",
            file=sys.stderr,
        )
        return 1

    print("\n=== GATE SUMMARY ===")
    for status, count in report["counts"].items():
        print(f"{status.replace(' ', '_')}={count}")

    print(f"GATE: {gate}")
    print(f"FULL CI: {full_ci_status}")

    if report_file is not None:
        print(f"Report: {report_file.relative_to(ROOT)}")

    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
