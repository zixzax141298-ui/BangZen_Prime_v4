# Architecture

Layers (dependencies point inward):

- `bangzen_prime/domain`: pure model. Values (Decimal, UTC), tokens and pairs, safety
  assessment, signals with long-only price geometry, risk arithmetic, order state machine.
  No I/O imports.
- `bangzen_prime/application`: use cases (`AuditTokenUseCase`, `ScanMarketUseCase`,
  `build_signal`), ports (`MarketDataPort`, `TokenSafetyPort`, `Notifier`), indicators,
  scoring, event bus, outbox worker, risk engine, paper trading orchestration.
- `bangzen_prime/infrastructure`: SQLite persistence and migrations, resilience policies
  (retry, circuit breaker, token bucket, health), HTTP transport, DexScreener and RugCheck
  adapters, Telegram adapter, simulated execution.
- `bangzen_prime/interfaces`: CLI and offline demo.
- `bangzen_prime/bootstrap.py`: composition root. The only place that wires concrete classes.

Data flow for one scan of one token:
1. Market fetch (outside any transaction) selects the most liquid matching pair.
2. Staleness is checked against the decision time.
3. Safety fetch. Rugged or over-threshold tokens are rejected before scoring.
4. One transaction writes token, pair, safety, price sample, signal, outbox row, and audit entry.
5. The outbox worker dispatches events to subscribers. Each subscriber is deduplicated.
6. Accepted signals reach the notifier. Failures leave the row pending for retry.

Paper flow: accepted signal -> `RiskEngine.evaluate` (audited) -> exposure reservation ->
`SimulatedExecution.submit` (idempotent) -> `on_price` closes at stop or target -> ledger.
