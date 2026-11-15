# Stages and status

| Stage | Scope (brief) | Status |
|---|---|---|
| 1 | Foundation, config, logging, errors, CLI, CI | Done. CI workflow written, not executed on a hosted runner. |
| 2 | Domain core | Done. |
| 3 | SQLite, migrations, UoW, outbox, audit chain | Done. Sync `sqlite3`, not `aiosqlite` (see KNOWN_LIMITATIONS). |
| 4 | Market data, safety, resilience | Done with mocked transports. |
| 5 | Scanner, scoring, signals, event flow, notification | Done. |
| 6 | Telegram signal-only | Adapter and tests done. Not exercised against Telegram. |
| 7 | Risk engine | Done. Exposure reservations tested under concurrency. |
| 8 | Execution dry-run | Done. Paper only. |
| 9 | Controlled integration: quote, RPC simulation, reconciliation | Done as controlled, mock-tested validation pipeline. **Broadcast is locked.** No signing key, no RPC endpoint, no devnet or mainnet call was made. See "Stage 9 boundaries". |
| 10 | Hardening and operations | Done for supervisor, metrics, health, DB busy handling, backup/restore, retention. Not done: Docker image, dependency/security scanner run, load test against a real DB. |
| 11 | Validation, packaging, handover | Done for: seeded paper soak with invariants, offline demo, wheel build and clean-venv install, test/coverage reports, release notes, ZIP with manifest. Not done: replay/backtest (no historical data in the project), real-API smoke test (opt-in, needs network). |

## Stage 9 boundaries

The pipeline is: quote -> validate quote (provider allowlist, mints, amount, expiry, price
impact) -> build plan -> inspect plan (programs, fee payer, sources, destinations, totals) ->
simulate -> stop (VALIDATE_ONLY or SIMULATE_ONLY). BROADCAST is refused unless the caller
explicitly passes `broadcast_allowed=True`, and `BANGZEN_BROADCAST_ENABLED` must stay false (the
configuration rejects true). The only signer is `DisabledSigner`. Tests inject a fake signer
that holds no key material. Using a real signer requires owner approval and a separate security
review, as the brief states.

## Stage 10 and 11 notes

- Supervisor: failures are isolated per worker, repeat failures disable a worker, emergency stop
  skips order-placing workers, and shutdown finishes the current cycle.
- Soak: `bangzen-prime soak --cycles 200 --seed 7`. The market is a seeded random walk with
  zero drift. Paper PnL from this run is a model output for testing invariants. It is not
  evidence of strategy performance.
