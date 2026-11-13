# Change Ledger — CI cascade import + execution mode wiring

## Objective
Restore CI: fix cascade import from package `__init__`, restore overwritten `use_cases.py` (Scan/Audit), align bootstrap with `ExecutionUseCase`/`ExecutionPlan` for 3 operating modes.

## Non-goals
- Enable live trading by default
- Weaken or delete unit tests
- Change risk thresholds

## Operating mode
Targeted modes remain TELEGRAM_ONLY (default), EXECUTION_ONLY, HYBRID. Live path remains gated by Settings + policy + adapters.

## Files changed
- `bangzen_prime/__init__.py` — remove bootstrap import (break cascade)
- `bangzen_prime/application/use_cases.py` — restore ScanMarketUseCase / AuditTokenUseCase / SignalPolicy
- `bangzen_prime/bootstrap.py` — correct imports; event handler builds ExecutionPlan (not Signal)

## Security impact
- Fail-closed defaults preserved
- No secrets added
- Live execution still requires LIVE_TRADING + burner key + mode

## Validation
Commands to run after merge-ready checkout:
```
python3 -m compileall -q bangzen_prime tests scripts tools
python3 scripts/run_tests.py
python3 tools/ci.py --profile auto
```
Status at PR open: NOT RUN on Actions for this head (owner must verify GREEN).

## Rollback
Revert this PR commit on branch `fix/ci-cascade-import-execution-modes`.
