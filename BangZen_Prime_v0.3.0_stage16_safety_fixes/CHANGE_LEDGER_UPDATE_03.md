# Change Ledger — Update 03 (research evidence gates, stage 11 draft)

Base: `BangZen_Prime_v4_stage10_all_tests_pass.zip`, SHA-256
`44b6bc3a30128f567d2f52d063e74ff1e45153bdeb60c6a5fae16f891f71b512`
(no git metadata in the package, so no commit SHA is recorded).

## Corrections
- Update 02 and `docs/STRATEGY_RESEARCH.md` named `bangzen_prime/application/backtesting.py`.
  The module is `bangzen_prime/research/backtesting.py` (`docs/STRUCTURE_MIGRATION_2026.md`).
  `docs/STRATEGY_RESEARCH.md` now uses the correct path. Update 02 itself is left unchanged.
- The 9 test errors in the stage-10 baseline came from `ModuleNotFoundError: httpx` in the
  test environment. The code and tests were not at fault. `scripts/run_tests.py` now checks
  declared dependencies first and exits with a clear message if one is missing.

## Added
- `bangzen_prime/research/cost_model.py`: explicit cost model. Unmeasured inputs produce
  `UNAVAILABLE` with the missing names. Nothing is defaulted to zero. Slippage uses a linear
  liquidity term, which is an assumption and not a calibrated curve. Priority fees use
  geometric retries, `2 * fee / (1 - p)`.
- `bangzen_prime/research/walk_forward.py`: chronological development / validation / test
  split, per-phase replay, buy-and-hold and no-trade baselines, and contiguous test folds.
  Candidates are assigned to phases by signal candle.
- `bangzen_prime/research/config_freeze.py`: SHA-256 of canonical JSON. Floats and naive
  datetimes are rejected.
- `bangzen_prime/research/readiness_gate.py`: deterministic gate. Output is `NOT_READY` or
  `HUMAN_REVIEW_CANDIDATE`. `live_trading_allowed` is a constant `False` and cannot be set.
  Missing evidence is a failed check.
- Tests: `tests/unit/test_cost_model.py`, `test_walk_forward.py`, `test_readiness_gate.py`,
  `test_config_freeze_and_fixed_cost.py` (52 new tests). The readiness-gate tests include
  live-lock checks: the gate cannot be built with live enabled, its module imports nothing from
  execution, security, bootstrap, notifications, data, or network modules, and `Settings`
  still rejects `LIVE_TRADING` and `BROADCAST_ENABLED`.

## Updated
- `bangzen_prime/research/backtesting.py`: `BacktestConfig.fixed_cost_per_trade` (default 0,
  validated non-negative). Default behaviour is unchanged; the existing 11 backtest tests pass
  unchanged.
- `scripts/run_tests.py`: declared-dependency precheck (`httpx`, `defusedxml`). Exit code 2
  and no tests run when one is missing. Test discovery and pass/fail rules are unchanged.
- `docs/STRATEGY_RESEARCH.md`: corrected module path; new section for the stage-11 modules
  and their known gaps.

## Explicitly unchanged
- `AI_RULES.yaml`, `RULES.md`, `SECURITY.md`: not modified. RT-06 and the safety rules are not
  changed.
- Strategy weights, RSI periods, score thresholds, stop and target multipliers.
- Signing, private keys, transaction builder, RPC send, broadcast, and the live execution path.
- Live and broadcast lock in `core/config.py`.
- All existing modules and tests. No test was deleted, skipped, or weakened.

## Threshold proposals (not approved)
`GateThresholds` defaults are proposals and need owner approval under AI_RULES
`risk_policy.thresholds_change_requires`: 30 validation trades, 30 test trades, 20% test
drawdown, 4 folds, 60% positive folds, 50 forward paper trades, 20% forward drawdown.

## Validation performed
Environment: Python 3.13.18. `httpx` 0.28.1 was taken from a local package cache, because PyPI
was unreachable. `defusedxml` was already installed.
- `scripts/run_tests.py` with httpx available: 930 tests, 930 passed, 0 failed, 0 errors,
  0 skipped.
- `scripts/run_tests.py` without httpx: PRECHECK FAILED with the dependency named. No tests run.
- `python -m compileall -q bangzen_prime tests scripts`: passed.
- `python scripts/check_unused_imports.py`: 6 findings, all pre-existing
  (`strategies/__init__.py` x3, `core/interfaces/dashboard.py`, `tests/e2e/test_v3_flow.py` x2).
  None in new or changed code. The baseline had the same findings. NOT FIXED here.
- `tools/ci.py --profile termux`: LOCAL PASS (2 PASS), 9 NOT_RUN (Black, Ruff, Mypy, Bandit,
  Semgrep, Safety, Pip-Audit and related tools not installed).
- Tests printing `FAIL: test — Exit code 2` are output from a self-test that runs a failing
  command on purpose. The summary reports 0 failed.

## NOT_RUN / BLOCKED / unverified
- Hosted GitHub Actions CI: not run.
- Termux and VPS installation scripts: not run on a device or VPS.
- Live Solana data, RPC, and provider APIs: not reached (no network).
- Black, Ruff, Mypy, Bandit, Semgrep, Safety, Pip-Audit: NOT_RUN.

## Known limitations
- No point-in-time historical collector. The coverage flags in the gate are declarations and
  are not verified against data.
- No forward paper record producer. The gate fails closed when it is missing.
- Drawdown is realised-trade drawdown only, not mark-to-market.
- Each candidate is evaluated at a fixed notional with no concurrent capital limit.
- Gate thresholds are proposals.
- No profit or safety claim is made. The gate output is `HUMAN_REVIEW_CANDIDATE` at most, and it
  is not a trading authorisation.
