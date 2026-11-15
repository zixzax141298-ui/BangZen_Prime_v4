# Change ledger: v4 hardening pass

Objective: fix verified defects that made paper results optimistic or let risk limits fail open.
Scope: paper-only. No signing, broadcast, or live path was enabled.

## Behaviour changes (each pinned by tests/unit/test_hardening_v4.py)

| Area | Before | After |
|---|---|---|
| Position sizing | Ignored slippage; realised loss at stop was ~9% over budget | `size_position(slippage_rate=...)` uses the same adjusted fill/exit prices as the executor |
| Stop-loss gap | Booked at the stop level regardless of actual price | Stop-market semantics: fills at `min(price, stop)`, then slippage |
| Equity / drawdown | Realised PnL only; open losses invisible | Mark to market; unknown mark values position at its stop (pessimistic) |
| RiskGovernor | Called with hardcoded zeros; limits never fired | `DbRiskStateReader` supplies real open positions, signals today, portfolio risk, daily loss; missing state refuses |
| Spread | Hardcoded 0, so `SPREAD_TOO_WIDE` never fired | Unknown spread -> `SPREAD_UNAVAILABLE` (fail closed) |
| Paper fill price | Signal-time entry | Current market price; invalidated geometry rejected |
| Missing market price | Fill at price 1 (fabricated) in `ExecutionUseCase` | Reject `MARKET_PRICE_UNAVAILABLE` |
| Notional | `amount_raw * price` (atomic units treated as whole tokens) | Converted with `input_decimals`; missing decimals -> `DECIMALS_UNKNOWN` |
| Position closing | Only demo/soak could close paper orders | `settle_open_positions()` closes on current price; unknown price keeps position open |
| Monitor budget | Duplicates spent provider budget; budget raised mid-cycle | Duplicates skipped without spend; `_spend` returns bool; watchlist rotates |
| Phase tracking | Unobserved results recorded as phase `UNKNOWN` | `ScanResult.phase` is `None` when unobserved; no fake transitions |
| Scan cooldown memory | Unbounded dict | Expired entries pruned |
| Volume evidence | `volume_24h > 0` | `volume_24h >= MIN_VOLUME_24H_USD` (default 5000) |
| Telegram timeouts | Retried; sendMessage is not idempotent, so duplicates were possible | Not retried (delivery unknown); 5xx and 429 still retried |
| Telegram length | Code points | UTF-16 code units (Telegram's counting) |
| `.env` parsing | Inline `# comment` became part of the value | Stripped for unquoted values; quoted `#` kept |
| `MAX_OPEN_POSITIONS` | `0` accepted, then failed later | Rejected at settings time (min 1) |
| Packaging | `dependencies = []` but bootstrap imports httpx | `httpx` and `defusedxml` are base dependencies |
| Docker | Default command exits; restart loop; DB lost on recreate | `command` runs monitor; DB on `./data` volume |
| Legacy key code | `bangzen_prime/core/` with solders keypair and base58 signing | Package removed |

## Test changes that were deliberate

- `test_stop_loss_closes_with_negative_pnl` expected exit at the stop level for a gap. Updated to the real price, because the old expectation encoded the bug.
- `test_timeout_is_retryable` now asserts timeouts are not retried. Updated for the non-idempotent send.

## Not verified here

- 12 test modules import `httpx` and could not run in this sandbox (network off). They include sybil and commander safety tests. Run `pip install -e ".[dev]"` and the full suite locally.
- demo and soak still open zero orders on synthetic data. Opening is covered by unit tests of `PaperTradingUseCase`, not by an end-to-end run.

## Open questions for owner

- Paper notional semantics: the plan now prices the spent (input) token. Confirm this matches the intended execution model before any use.
- Spread source: no bid/ask in pair data, so paper entries are rejected until a spread or price-impact source is wired (for example a Jupiter quote round trip).
