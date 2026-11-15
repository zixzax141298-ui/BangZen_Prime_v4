# Change Ledger: Stage 1, HALT.flag kill switch and emergency-stop coverage

## Objective
Implement the HALT.flag kill switch required by AI_RULES `non_negotiable_safety.halt_flag`
(blueprint 11.2 and 21), and make the existing emergency stop (`BANGZEN_EMERGENCY_STOP`) apply to
every decision-producing path that was missing it: `monitor`, outbox delivery, and the WebSocket
listener.

## Non-goals
- No change to the Supervisor. It is not used in production; its test encodes the current
  "skip only order-placing workers" behaviour. Requires owner decision.
- No change to governance files (AI_RULES.yaml, AGENTS.md, SECURITY.md, RULES.md). Their
  "NOT IMPLEMENTED" status lines are now outdated and need owner approval to update.
- No live-trading, signing, or broadcast change.

## Base and head
- Base: BangZen_Prime_v4-main as supplied in the zip (no git metadata available; base SHA not recorded).
- Head: not applicable (no repository access in this session).

## Changed files
- NEW `bangzen_prime/application/halt.py`: `halt_flag_engaged(path)` (fail-closed) and
  `halt_engaged(emergency_stop, path)`.
- `bangzen_prime/application/monitor.py`: `halt_check` check before each cycle; `CycleReport.halted`.
- `bangzen_prime/application/outbox_worker.py`: `halt_check` check before claiming any row.
- `bangzen_prime/bootstrap.py`: outbox worker uses `halt_engaged(settings.emergency_stop)`.
- `bangzen_prime/interfaces/cli.py`: refuses `scan`, `discover`, `outbox`, and `monitor` when
  halted (was: `scan`, `discover`, `outbox` only, and only the env switch). Monitor receives the halt check.
- `bangzen_prime/interfaces/ws_cli.py`: refuses to start when halted; each transaction callback
  returns early when `HALT.flag` is present.
- `bangzen_prime/application/secure_execution_gateway.py`: paper-open emergency check honours `HALT.flag`.
- NEW `tests/unit/test_halt_flag.py`: 9 tests.

## Compatibility
- Defaults keep old behaviour when no flag file exists and the env switch is off.
- Monitor now returns a `halted` field in its JSON cycle report (additive).
- Monitor keeps running while halted, idling and logging a warning each cycle, so it resumes
  automatically when the flag is removed. Operators who want a hard exit must stop the process.

## Security impact
- Decision production (Monitor scans, signal acceptance, Telegram alerts via the outbox, and the
  WebSocket "SMART MONEY" alert) stops while `HALT.flag` exists or the env switch is on.
- Fail-closed: a flag whose state cannot be determined counts as engaged.
- Known limit: the flag path is relative to the working directory (`HALT.flag` in the process CWD).

## Tests executed
- `python3 -m unittest tests.unit.test_halt_flag -v`: 9 passed.
- Full suite, verification-only run with a stub `httpx` module (the real package is not installable
  in the session). Baseline: 902 tests, 887 passed, 7 skipped, 3 failures, 5 errors. This change:
  911 tests, 896 passed, 7 skipped, 3 failures, 5 errors. Per-test comparison: no pre-existing test
  changed status; the 9 new tests pass. The 8 failing or erroring tests (`tests.e2e.test_paper_flow`,
  `tests.e2e.test_v3_flow`) fail identically on the baseline, so they are not caused by this change.
  They may be caused by the stub and were not investigated.

## Checks not run
- `python3 tools/ci.py` (full gate): not run. Cargo test needs network access that is blocked.
- Real `httpx`-backed tests: not run; the stub replaces httpx.
- Bandit, pip-audit, Semgrep, Ruff, Mypy: not run (not in the gate).

## Known limitations
- `bootstrap.py` passes the static `emergency_stop` value to the RiskEngine policy at startup. A
  flag created later is not seen by the RiskEngine, but it is seen by the execution gateway on every call.
- The Supervisor still skips only order-placing workers under the env switch (unchanged).

## Rollback
Revert the files listed above and delete `bangzen_prime/application/halt.py` and
`tests/unit/test_halt_flag.py`. No data, schema, or configuration changes.
