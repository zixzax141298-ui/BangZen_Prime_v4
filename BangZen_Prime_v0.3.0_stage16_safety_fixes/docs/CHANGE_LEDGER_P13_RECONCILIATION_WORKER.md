# Change Ledger P13 — ReconciliationWorker and test-fake protocol alignment

## Objective and non-goals
- Objective: implement the balance reconciliation worker that the v3 test contract requires (mismatch trips emergency latch; RPC outage is UNAVAILABLE, not mismatch; tolerance validated); fix a stale test fake whose transport signature did not match production.
- Non-goals: no change to live-execution lock, risk thresholds, sizing, SL/TP, fees, slippage, or safety filters. No new providers. Lifecycle evidence producers and phase vocabulary are not changed here.

## Files changed
- bangzen_prime/application/reconciliation.py: kept the existing `CircuitBreaker` code unchanged; appended `ReconciliationWorker`, `ReconciliationResult`, `BalanceProvider`, and status constants.
- tests/unit/test_reconciliation_worker.py (new): 11 tests covering open-order accounting, other-mint isolation, tolerance boundary, mismatch audit + latch, string normalisation, invalid balances (negative, non-numeric, NaN, Infinity) failing closed, provider outage, NOT_CONFIGURED, owner passthrough, constructor validation.
- tests/support.py: `RecordingTransport.__call__` accepts both the legacy `(url, timeout)` shape and the `HttpRequest` shape used by production `request_json`. Assertions in tests are unchanged.
- docs/CHANGE_LEDGER_P13_RECONCILIATION_WORKER.md (this file).

## Design
- Expected units = sum of `filled_units` for orders in `FILLED` or `PARTIALLY_FILLED` for the mint. `CLOSED`, `NEW`, `REJECTED`, `TIMEOUT` are excluded. No open orders means expected 0.
- Tolerance is a percentage of expected units. With expected 0, the match must be exact.
- Mismatch: trips `EmergencyLatch` and appends a `ReconciliationMismatch` audit row in one DB transaction.
- Unavailable/invalid balance: returns UNAVAILABLE, never OK, never trips the latch.
- Application layer imports `Database`/`AuditLog` from infrastructure; this follows an existing precedent (`secure_execution_gateway.py`).
- Read-only: no signing, submission, or broadcast.

## Known limitations (owner review required)
- The latch's audit callback is not wired to the database by this worker. The `EmergencyStopTriggered` event is not persisted to `audit_log` unless the caller supplies an audit callback to `EmergencyLatch`.
- Expected units come from paper orders too. In paper mode the on-chain balance is zero, so the worker must stay `balances=None` (NOT_CONFIGURED) until live execution is separately approved. Otherwise paper orders would produce false mismatches.
- `CircuitBreaker` is duplicated in `application/reconciliation.py`, `application/resilience.py`, and `infrastructure/resilience/policies.py`. Not consolidated here.

## Validation actually run (offline; httpx, black, ruff, mypy, bandit, semgrep, pip-audit not installable here)
- Full `python3 scripts/run_tests.py`: 756 discovered, 747 passed, 0 failed, 9 errors. All 9 are `ModuleNotFoundError: httpx` in modules that import the httpx-backed adapter stack (e2e flows, CLI, sybil/signal gate tests). Earlier baseline: 12 errors, of which the new work removes `tests.integration.test_v3_adapters` (now imports and passes) and the two `SolanaTrackerHolderEvidenceTest` TypeErrors (fixed by the support change).
- `tests.integration.test_v3_adapters`: loads and runs with no failures.
- Contract class `ReconciliationTest` (5 tests) executed directly: all OK.
- New `tests.unit.test_reconciliation_worker`: 11 tests OK.
- Mutation checks on a scratch copy: including CLOSED in open statuses causes 1 failure; disabling tolerance check causes 3 failures. Test suite detects both.
- `py_compile` on all changed Python files: OK.

## Checks NOT run and why
- `python3 tools/ci.py` full gate: NOT RUN. Lint/type/security tools not installable offline.
- 9 httpx-dependent modules: NOT RUN.
- `ai_commander._load_tools` change (from P12): not executed, module depends on httpx.

## Rollback
Revert the appended worker block and the new test file; revert `tests/support.py` to the single-signature `__call__`. No migration, no config change.

## Status
Implementation: complete for step 1 scope. Test (offline): PASS for all runnable tests. CI gate: NOT RUN / NOT GREEN. Review: pending owner. Merge: not performed. Live execution: remains locked.
