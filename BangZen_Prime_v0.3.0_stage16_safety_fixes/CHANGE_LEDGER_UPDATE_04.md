# Change Ledger — Update 04 (forward paper record, follows Update 03)

## Added
- `bangzen_prime/research/forward_paper.py`: append-only, hash-chained forward paper ledger.
  - Frozen configuration hash checked on every trade; duplicate trade IDs refused.
  - Metrics: expectancy, win rate, profit factor (undefined without losses), realised
    max drawdown, exposure, mean holding time, per-lifecycle-phase counts. Empty ledger
    returns no values, not zeros.
  - `summary_for_gate()` feeds `readiness_gate.ForwardPaperSummary`. Empty ledger gives None,
    so the gate reports the record as missing.
  - Save and load as JSONL. Load refuses a broken hash chain.
- `tests/unit/test_forward_paper.py`: 13 tests.

## Validation
- `scripts/run_tests.py` with httpx on PYTHONPATH: 943 passed, 0 failed, 0 errors, 0 skipped.
- `python -m compileall -q bangzen_prime tests scripts`: passed.
- `scripts/check_unused_imports.py`: same 6 pre-existing findings, none in new code.

## Limits
- Paper only. The ledger records trades supplied by a caller. It does not generate them, so
  no forward evidence exists yet.
- Metrics are realised-trade metrics, not mark-to-market.
- Thresholds in `GateThresholds` remain unapproved proposals.

## Added (later in update 04)
- `bangzen_prime/execution/forward_recording.py`: copies CLOSED paper orders into the forward
  ledger. Refuses open orders and orders missing PnL, exit, fill, or close fields. Records
  lifecycle phase as "unknown" unless the caller supplies one. Idempotent sync by order id.
  Lives in execution/ because it reads OrderRecord; research/ keeps no execution imports.
- `tests/unit/test_forward_recording.py`: 6 tests.
- Full suite after this change: see run_tests SUMMARY in the session report.
