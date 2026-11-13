# Known limitations

Environment limits (this build):
- No network. Real DexScreener, RugCheck, Telegram, Solana RPC, and quote-provider calls were never
  made. Only fakes were used.
- pytest, ruff, mypy, coverage.py, aiosqlite, and `python -m build` were not installable. Tests run
  under `unittest`. Coverage is an approximate stdlib line tracer. Branch coverage is not measured.
- Hosted CI run 43139555906 passed on lifecycle branch head `d1cdcab20cd1f513d9e18bad051a4b0841f0725d`: 434/434 tests on Python 3.11 and 434/434 on Python 3.12, plus compile, import hygiene, Rust build, and wheel verification. The workflow does not yet enforce the full owner-requested N16 security/type/lint gate; `tools/ci.py`, `AI_RULES.yaml`, `AGENTS.md`, `RULES.md`, and root `SECURITY.md` are absent from current main.
- `uv.lock` was not generated. There are no third-party runtime dependencies to pin.

Architecture deviations:
- The application layer imports some infrastructure types directly (UnitOfWork, Database, audit
  and attempt stores, the signer exception). Domain has no such imports. Moving these behind ports
  is planned work, not done.
- Persistence is synchronous `sqlite3` with a process-local lock, not `aiosqlite`.
- Migration 0002 was edited, and 0003 added, before any release. Do not edit either after release.

Chain (Stage 9):
- No real quote provider, route builder, RPC client, or signer exists. Only ports and fakes.
- Devnet support is not implemented. The brief says it depends on the route provider.
- The simulation result is whatever the RPC port returns. Nothing was simulated on a real chain.
- Balance reconciliation is a helper function. It is not wired into the broadcast path.
- No Jito or other private-relay integration, as the brief requires.

Product and model:
- RugCheck schema and score direction come from third-party documentation. Unverified.
- Signals use close-price history stored by this application. No candles. A token needs 15 samples
  before any accepted signal.
- Volatility is a close-only proxy (mean absolute change), not ATR from high/low data.
- Spread is not part of the pair snapshot, so it is recorded as zero. The spread gate never triggers
  in paper mode.
- Paper slippage is a fixed rate, not a liquidity-based estimate.
- Scoring is heuristic. Confidence is total/100. It is not a probability.
- Continuous discovery uses DexScreener latest token profiles as a candidate feed, not a guaranteed new-pair or complete Solana launch feed; coverage and API schema/rate limits require live validation. Candidate lifecycle state and phase history are now persisted in SQLite, but discovery cooldown memory remains process-local and resets on restart. Only the initial DISCOVERED phase is currently populated; evidence-driven classification is not implemented yet.
- The soak market has zero drift by design. Its PnL is a model output, not performance evidence.
- Replay and backtest were not done. The project contains no historical market data.

Delivery and concurrency:
- Notification delivery is at-least-once. A crash between send and record can cause a duplicate.
  Exactly-once is not claimed.
- Paper opens are serialised by one lock in a single process. Multiple processes sharing a database
  rely on SQLite's write lock and were not tested under contention.
- Supervisor disable state lives in memory. A restart clears it.

Operations:
- No metrics HTTP endpoint. Metrics are in-process and rendered as Prometheus text on demand.
- No Docker image. No load test against a real database.
- Dependency and security scanners were not run.
- No CLI command re-enqueues FAILED outbox rows. Recovery is a manual, recorded database change.
- Disk-full and power-loss behaviour were not tested. Busy-lock behaviour was tested with a second
  connection holding an exclusive lock.
- The CLI has no command to open or close paper orders. Paper trading runs through the library API
  and the offline `demo` and `soak` commands.

Not financial advice. Heuristics do not guarantee profit or safety.

Added in 0.2.0:
- Rust crate native/rust was NOT compiled. No Rust toolchain existed in the build environment.
  Tests cover the Python fallback. A Rust-vs-Python equality test runs only when the module loads.
- Yellowstone gRPC: protobuf stubs are not included. The live client refuses to start.
- Birdeye: only `token_overview` was verified (path and headers). The field names `liquidity`,
  `v24hUSD`, and `price` are unverified. A response without them is rejected.
- Solana Tracker: `/tokens/{mint}/holders` (total and accounts) was verified. The top-10 share is
  computed over the returned accounts, not over total supply.
- Jupiter: the docs mark the Metis quote API as no longer actively maintained and superseded by
  Swap V2. The quote adapter uses /swap/v1 and must be re-checked. priceImpactPct is treated as percent.
- Jito: getTipAccounts and tip_floor were verified in public docs. The tip_floor field name
  `landed_tips_50th_percentile` and its SOL unit are unverified.
- Helius: standard Solana RPC methods. The key travels in the query string as Helius requires.
- AI model identifiers (BANGZEN_AI_MODEL defaults) are not verified against the providers' live lists.
- The reconciliation worker is a class. It is not wired into bootstrap, because no live balance
  source is configured in this release.
- Nothing in this release has contacted a live network, a market API, an AI provider, or a chain.


## Live execution readiness audit (2026-11-12)

The current repository must not be described as production-ready for live funds:
- The old unresolved `LiveExecutor` composition path has been removed from `bootstrap.py`; the container deliberately exposes no live executor.
- The former execution CLI's hard-coded illustrative purchase simulation has been removed. It now reports scanner results only and explicitly marks execution as NOT_ATTEMPTED.
- The Jupiter adapter is quote-only. No production transaction builder and no production Solana RPC send/reconciliation adapter are wired into the composition root.
- `WalletSigner` signs a serialized transaction, but it is not integrated into a complete validated quote -> built transaction -> inspected plan -> simulated transaction -> signed transaction -> RPC broadcast pipeline.
- `ControlledExecution` has a broadcast seam and fake-based tests, but bootstrap does not provide a real builder/RPC implementation. The default signer remains disabled.
- Smart-money analysis is not wired into scan approval: the adapter currently consumes pre-fetched RugCheck/trade payloads and does not implement the `analyze_token(mint)` method expected by the scanner. Helius credentials alone do not make this analysis available.

These are implementation gaps, not reasons to pretend that live execution is enabled. Keep the live execution work explicitly blocked until a real transaction builder, RPC adapter, wallet/address verification, emergency-stop enforcement, quote freshness/slippage checks, transaction simulation, idempotent send/reconciliation, balance reconciliation, and dedicated end-to-end tests are implemented. Never replace missing checks with permissive defaults.

Remediation in this branch:
- EV inputs are validated as finite Decimal values with explicit range and geometry checks.
- Legacy `OWNER_PRIVATE_KEY` is rejected from both process and injected environment mappings.
- Configured intel evaluation errors fail closed; the incomplete smart-money adapter is no longer wired based only on the presence of a Helius key.
- Regression tests cover EV invalid inputs, injected legacy owner-key rejection, and intel failure behavior.

Validation boundary: a green GitHub CI run only proves the checks actually configured in `.github/workflows/ci.yml`; it is not proof of real-network, real-wallet, or live-transaction safety.


## Live execution workstream update (2026-11-12, branch `feat/live-execution-ai-jupiter-v2-jito`)

Implemented in this branch:
- AI response parsing now requires one exact JSON object with exactly three fields; duplicate keys, additional keys, surrounding prose, invalid confidence, and malformed output are rejected.
- AI evaluation fails closed for provider exceptions and malformed contexts. The gate never returns approval when context construction fails.
- Holder concentration and holder count are required evidence. The current scanner does not yet have a verified holder-data source wired into this AI context, so AI returns `SKIP` until that integration exists.
- Added unit tests for malformed AI responses, missing holder evidence, provider exceptions, and gate context failures.
- The controlled broadcast use case now refuses BROADCAST without an explicit model-origin `AIDecision(BUY)`; fallback decisions, AI vetoes, invalid confidence, and missing gates are rejected before requesting a quote or signing.
- Added a standalone Jupiter Swap API V2 adapter for `GET /order` and `POST /execute`. It validates mints, raw input amount, transaction base64 and packet size, returned amounts, router/version, and router-specific expiry metadata. The execute call is deliberately not automatically retried because a timeout can have an unknown on-chain outcome.

Still blocked; this branch is NOT live-fund ready:
- The Jupiter V2 adapter is not yet wired into a production executor, wallet signer, controlled transaction inspection, RPC simulation, broadcast, or balance reconciliation.
- The current Jupiter order adapter accepts only transaction version 0. It does not yet decode the message to independently inspect every instruction/program/account before signing.
- When AI is enabled, the scanner now fetches holder count and top-10 concentration from the configured Solana Tracker holder endpoint. The top-10 share is computed over returned holder accounts, not total token supply; this metric must not be described as total-supply ownership concentration. Missing, malformed, mismatched-mint, or empty holder evidence rejects the candidate before the model call.
- `Settings` now unconditionally rejects `LIVE_TRADING=true` and `BROADCAST_ENABLED=true`, even if burner and Helius credentials are present. The bootstrap has no live executor composition path.
- Jito tip planning/bundle relay is not integrated into an idempotent live execution and reconciliation path. Do not combine Jupiter `/execute` and Jito bundle relay for the same signed transaction.
- No real wallet signing, mainnet simulation, mainnet broadcast, buy/sell lifecycle, or post-trade balance reconciliation has been tested.
- Existing CI does not run the full requested engineering gate (Black, Ruff, Mypy, Bandit, Semgrep, Safety, Pip-Audit, Pytest, and Cargo Audit as mandatory checks). It currently builds the Rust extension, compiles Python, checks unused imports, runs the repository test runner, and verifies the wheel on Python 3.11/3.12.

Never interpret a successful Jupiter HTTP response as sufficient evidence of final settlement. The production executor must persist intent before sending, use a stable idempotency key, record unknown outcomes, reconcile the signature and balances, and never blindly resubmit after a timeout.


## Additional hardening (2026-11-12, follow-up)

- Live and broadcast flags are now explicitly blocked at settings construction. Supplying credentials cannot unlock a non-existent production execution pipeline.
- The unresolved `LiveExecutor` import was removed from bootstrap. `live_executor` remains `None` by design.
- The execution CLI no longer prints a simulated successful purchase based on a hard-coded price. It reports signal state and `execution: NOT_ATTEMPTED`.
- Controlled execution now persists the unique idempotency intent as `UNKNOWN` before signing or calling the network. If the process crashes after submission but before recording a signature, the same key cannot initiate a second send. Unexpected send exceptions and missing signatures remain unresolved/UNKNOWN rather than being retried.
- Added a typed `ai_decision_gate` adapter matching the controlled execution pre-trade contract. Context failures return a fallback `SKIP`.
- Regression tests added for credential-present live flag rejection, typed AI gate behavior, and unexpected ambiguous send failures.

These changes improve fail-closed behavior; they do not complete live execution. There is still no production transaction decoder/builder, signing pipeline, real RPC/Jupiter/Jito execution composition, holder evidence source, or live buy/sell lifecycle. No real signing or network broadcast was performed.


Holder evidence integration update:
- The scanner consumes `SolanaTrackerAdapter.holder_profile(chain, mint)` through a typed application port.
- AI receives an explicitly named `top10_holder_share_pct` metric and the reported total holder count.
- The provider is queried only when AI is enabled. If no Solana Tracker key/provider is configured, the candidate is rejected as `SAFETY_UNAVAILABLE`; there is no fabricated fallback.
- The top-10 metric is calculated from the account balances returned by the provider and is not a total-supply percentage. It is an imperfect concentration proxy, not proof of decentralization.
