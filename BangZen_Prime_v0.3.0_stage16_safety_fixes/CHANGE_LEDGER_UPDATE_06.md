# Change Ledger — Update 06 (daily loss re-check at paper order open)

## Gap found
- `RiskGovernor` checks daily loss (limit 1%) only when a signal is created. A signal accepted
  earlier could be executed after the day's loss limit was reached. Paper order open had no
  daily-loss check of its own.
- The governor cannot simply be reused at order time. Its `signals_today` count already includes
  the signal being executed, so it would refuse the 50th signal by mistake.

## Added
- `risk/daily_loss.py`: `daily_loss_reason(pct, limit)`. Returns DAILY_LOSS_LIMIT, returns
  DAILY_LOSS_UNAVAILABLE for None or non-finite input (fail closed), and raises on invalid input.
- `risk/risk_state.py`: `daily_loss_provider(reader)` adapter. Returns None if the read fails.
- `tests/unit/test_daily_loss_order_gate.py`: 12 tests.

## Updated
- `execution/paper_trading.py`: `PaperTradingUseCase` takes optional `daily_loss_provider` and
  `daily_loss_limit_pct` (default 1.0). The check runs after the halt check and before sizing.
  Provider exceptions are treated as unknown. A bad limit fails at construction.
  Default provider None means the check is NOT applied. It must be wired in production.

## Not done
- No production bootstrap wiring of PaperTradingUseCase exists, so this gate is not active in
  any production path yet. It is active only where `daily_loss_provider` is passed (tests).
- Daily loss counts realised losses only. Unrealised risk is covered by the per-trade and
  portfolio-risk checks.
- Day boundary is UTC midnight.

## Validation
- `scripts/run_tests.py` with httpx on PYTHONPATH: 984 passed, 0 failed, 0 errors, 0 skipped.
- `compileall`: passed.
- `check_unused_imports.py`: same 6 pre-existing findings.

## Wiring (follow-up in this update)
- `core/interfaces/demo.py` and `core/interfaces/soak.py`: the operator paper entrypoints now pass
  `daily_loss_provider` and `daily_loss_limit_pct=RiskGovernor().daily_loss_limit_pct`.
  These are the only production constructions of PaperTradingUseCase. The gateway factory has no
  production caller and receives an already-built use case.
- Guard test `PaperEntrypointWiringTest` checks that both files keep the wiring.
- `python -m bangzen_prime demo` and `soak --cycles 200` produce output identical to the stage-10
  package. Both scenarios open no orders, so this check does NOT exercise the new gate.
