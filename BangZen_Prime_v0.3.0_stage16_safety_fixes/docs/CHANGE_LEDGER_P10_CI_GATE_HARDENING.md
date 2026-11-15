# Change Ledger — P10 CI Gate Integrity Hardening

- Objective: harden CI gate record integrity and add regression coverage without changing the repository's required checks or weakening existing tests.
- Non-goals: no strategy changes, no risk-threshold changes, no wallet or signer changes, no transaction execution changes, and no CI requirement bypass.
- Base branch: `main`
- Base SHA: `4d1dfcbfd0b525759a92c77e9e13805381eda9c2`
- Head branch: `fix/p10-ci-gate-integrity`
- Head SHA: pending commit.

## Files changed

- `tools/ci.py`:
  - Validate that every check record name matches its corresponding check definition.
  - Raise `ValueError` on missing or mismatched record identity, failing closed instead of evaluating potentially misaligned results.
- `tests/unit/test_ci_gate.py`:
  - Add CI gate regression tests, including mismatched and missing record-name cases.
- `tests/unit/test_ci_profiles.py`:
  - Update Termux profile assertions to reflect the complete check inventory and per-check profile applicability.
  - Verify that Black remains in the inventory but is not applicable to Termux.

## Compatibility and migration

- No configuration migration required.
- Existing check definitions and profile selection remain intact.
- Termux continues to run only checks applicable to its profile.

## Safety and security impact

- No wallet, private key, signer, transaction, broadcast, strategy, or risk-threshold behavior changed.
- Live execution remains locked.
- No existing tests were intentionally removed or weakened.
- CI gate now rejects check/record identity mismatches.

## Validation evidence

- `python -m unittest tests.unit.test_ci_gate tests.unit.test_ci_profiles -v`
  - PASS: 32 tests.
- `python scripts/run_tests.py`
  - PASS: 849 tests; 849 passed, 0 failed, 0 errors, 0 skipped.
- `python tools/ci.py --profile termux --report ""`
  - LOCAL PASS.
  - Compile and canonical unittest suite passed.
  - Full CI was NOT run; 9 profile-excluded checks reported NOT_RUN.
- `git diff --check`
  - PASS: no whitespace errors at the time of the check.

## Checks not run and limitations

- Full GitHub CI profile has not yet been verified.
- No claim is made that the complete mandatory CI gate is green.
- GitHub Actions must provide the authoritative Full CI result after the feature branch is pushed.

## Rollback

Revert the feature-branch commit containing these changes. Do not remove or bypass the mandatory CI gate.
