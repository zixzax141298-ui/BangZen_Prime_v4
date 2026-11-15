# Change Ledger — Update 08 (persist forward order phase)

## Added
- `storage/migrations/0006_forward_order_phase.sql`: table `forward_order_phase`
  (order_id PK -> orders.id, phase CHECK to LifecyclePhase names + UNKNOWN, recorded_at).
- `execution/forward_session.py`: phase is written once at order open (INSERT OR IGNORE) and read
  at settlement. It is no longer held in memory, so it survives restarts. Orders with no stored
  phase are labelled UNKNOWN.
- `tests/unit/test_forward_session.py`: restart test (phase survives a new session object on the
  same database).

## Test expectation updates (explicit, not weakened)
Adding migration 0006 changed the expected schema version list from [1..5] to [1..6] in six
exact-match assertions:
- `tests/integration/test_persistence.py`: 3 assertions (lines 58, 81, 93).
- `tests/e2e/test_cli.py`: 2 assertions (lines 65, 66).
- `tests/e2e/test_scan_flow.py`: 1 assertion (line 577, row count 5 -> 6).
Each assertion is still an exact match. No test was removed, skipped, or relaxed.

## Validation
- `scripts/run_tests.py` with httpx on PYTHONPATH: 992 passed, 0 failed, 0 errors, 0 skipped.
- `compileall`: passed.
- `check_unused_imports.py`: same 6 pre-existing findings.

## Not done
- Migration packaging: confirm `0006_*.sql` is included in the wheel build (pyproject package
  data). Not checked in this environment.
