# Change Ledger: Stage 2, CI gate integrity

## Objective
Stop the gate from passing with skipped tests, mispaired check/record results, or missing
blueprint quality and security checks. Sources: AI_RULES `engineering.testing` (no skipping,
no test weakening), `status_vocabulary` (NOT_RUN is not PASS), and blueprint section 20.

## Non-goals
- No lint or type fixes in the repository (Ruff 187, Mypy 101, Black 5 files were already failing
  on the original code). Those need a separate PR.
- No change to the termux profile's contents beyond Black's exclusion from it.
- No change to governance files.

## Base and head
- Base: BangZen_Prime_v4-main zip as supplied (no git metadata; no base SHA).
- Built on Stage 1 (HALT.flag). Head: not applicable (no repository access).

## Changed files
- `scripts/run_tests.py`: `--allow-skips` default 10 -> 0.
- `tools/ci.py`:
  - `evaluate_gate` pairs records to checks by name and order. Any mismatch raises
    `ValueError("name mismatch ...")` (fail closed). The old code paired by position only.
  - Added blueprint checks: Black, Ruff, Mypy, Bandit, Semgrep, Pip-Audit (profiles vps, github;
    Black is not in termux, as the profile test requires), and Cargo Audit (with Rust).
- `tests/unit/test_ci_gate.py`, `tests/unit/test_ci_profiles.py`, `tests/unit/test_v3_core.py`:
  removed the seven `@unittest.skip("Dev mode...")` decorators. No assertion was changed.
- Black formatting applied to the 13 files changed in Stages 1 and 2 only.

## Compatibility
- Any gate run now needs the listed tools installed. Absent tools are BLOCKED, which fails the gate
  closed. `pyproject.toml` extras (`dev`, `security`) and `ci.yml` already install them.
- Semgrep with the default config may need network access to fetch rules. Not verified.

## Security impact
- A skipped or mispaired required check can no longer produce a green gate.
- Two live-trading guard tests (`test_live_trading_is_blocked`,
  `test_broadcast_requires_live_trading`) run again.

## Tests executed
- Full suite with a verification-only stub for httpx: 911 tests, 903 passed, 3 failed, 5 errors, 0 skipped.
  Per-test comparison against Stage 1: 7 status changes, all from skipped to passed. No passing test failed.
  The 3 failures and 5 errors are the same pre-existing ones (`tests.e2e` paper flow and v3 flow).
- `tests.unit.test_ci_gate`, `tests.unit.test_ci_profiles`: all pass.

## Checks not run
- The full gate `tools/ci.py`: not green. Measured on this tree:
  - Black: 13 of 13 changed files clean. The repository still has pre-existing Black failures outside the changed set.
  - Ruff: 187 errors, same as the original code.
  - Mypy: 102 errors; 101 existed before this stage. The new one is the `halted` key in a dict in `cli.py`.
- Bandit, Semgrep, Pip-Audit, Cargo Audit: tools not installed in this environment, not run.

## Known limitations
- The gate is now stricter and reports NOT GREEN until lint and type debt is fixed or owner-approved
  exceptions are recorded. This is the intended behaviour under AI_RULES.
- The `termux` profile is left as before, so the local gate still excludes Black by design.

## Rollback
Revert `tools/ci.py`, `scripts/run_tests.py`, the three test files, and the Black formatting in the
listed files. Restore the `--allow-skips` default of 10 only through an owner-approved Change Ledger entry.
