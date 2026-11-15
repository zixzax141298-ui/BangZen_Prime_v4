# Release notes: 0.3.0 (paper only)

Added in 0.3.0:
- `bangzen-prime monitor`: continuous watchlist monitor with per-minute scan budget and phase-transition logging.
- Phase policy (`config/phase_policy.json`): per-phase evidence requirements, validated strictly.
- Phase gate runs after quality checks and only downgrades signals that would be accepted.
- `BANGZEN_MODE` accepts only `paper`. Live execution is not implemented.
- Per-provider API budget and Decimal-only data validation.
- Dashboard and intel dependencies moved to optional extras.

Not in 0.3.0: WebSocket/gRPC ingestion, persistent phase history, live execution.
