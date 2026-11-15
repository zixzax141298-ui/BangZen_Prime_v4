# Testing and Validation

## Canonical test runner

Run from the repository root:

```bash
python scripts/run_tests.py
```

The canonical suite uses Python stdlib `unittest` discovery and writes JUnit XML
to `reports/test-results.xml`. Preserve all existing tests and assertions.

Pytest is available for pytest-specific future tests. Do not run the same unittest
suite a second time through pytest and count duplicate execution as independent coverage.

## Portable validation gate

```bash
python3 tools/ci.py --profile auto
```

Profiles:
- `termux`: bytecode compilation and canonical unittest suite; avoids container/native tools.
- `vps`: full Python quality/security checks and Rust checks when its manifest exists.
- `github`: full checks used by GitHub Actions.
- `full`: alias for `github`.
- `auto`: detects Termux, GitHub Actions, or a general host.

PASS means the exact check ran and returned zero. Missing required tools/files are
BLOCKED and make the gate non-zero. Termux is a portable baseline, not a complete
security clearance.

The gate writes `reports/ci-report.json`; keep reports as local/CI artifacts.

## Full-profile prerequisites

```bash
python -m pip install -e ".[dev,security]"
cargo install cargo-audit --locked
```

If Rust lockfile is absent:

```bash
cargo generate-lockfile --manifest-path native/rust/Cargo.toml
```

## Security scans

Black, Ruff, Mypy, Bandit, Semgrep, and pip-audit run in full profiles.
Cargo fmt/test/audit run when `native/rust/Cargo.toml` exists.
Strix is a separate AI-assisted red-team assessment; it does not replace CI.
Safety CLI is supplemental and is not required by the portable gate.

## Evidence vocabulary

- PASS: exact check ran and passed.
- FAIL: exact check ran and failed.
- BLOCKED: required prerequisite was unavailable.
- NOT RUN: optional check was not executed.
- NOT APPLICABLE: component is absent or irrelevant to selected profile.

Never convert BLOCKED, NOT RUN, or unavailable security evidence into PASS.
