# Change Ledger — P1 Helius WebSocket Ingestion

## Scope
- Add a read-only Helius `logsSubscribe` WebSocket stream for one Solana address per subscription.
- Parse notifications into typed events only after validating required fields.
- Retry interrupted connections with bounded exponential backoff.
- Emit an explicit gap marker after reconnect so downstream consumers know historical reconciliation is required.
- Keep the Helius API key out of configuration repr and exception messages.

## Safety boundaries
- No wallet, signer, private key, transaction construction, swap, or broadcast code is added.
- This stream is not a historical data source and does not prove complete delivery.
- Consumers must persist checkpoints, deduplicate signatures, detect slot gaps, and reconcile missed data through HTTP/history sources before AI evidence can be marked complete.
- No AI decision, BUY authorization, strategy threshold, or risk limit is changed.
- Existing live-trading and broadcast locks remain untouched.

## Validation
- Unit tests added for subscription construction, address/commitment validation, valid and malformed notifications, failed transaction evidence, unrelated messages, and secret redaction.
- Tests have not been executed in this environment. No CI or test-pass claim is made.
