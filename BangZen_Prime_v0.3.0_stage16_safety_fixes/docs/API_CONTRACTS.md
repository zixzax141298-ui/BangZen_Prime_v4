# API contracts

## Outbound: DexScreener (market data)
- Used: `GET {base}/token-pairs/v1/{chainId}/{tokenAddress}` returns a JSON list of pairs.
  Checked against the public DexScreener API reference during the build.
- Not used: `/latest/dex/search` is a search endpoint, not a trending feed.
- Provider limit: 300 requests per minute for pair endpoints (token bucket in the adapter).
- Entries with a different chain, a different base token, malformed fields, or non-finite numbers
  are skipped and counted in a warning.

## Outbound: RugCheck (safety)
- Used: `GET {base}/tokens/{mint}/report/summary`, base `https://api.rugcheck.xyz/v1`.
- Field used: `score_normalised`, treated as 0 to 100 where higher is riskier.
- Field used: `rugged` (boolean), or a risk entry named `Rugged` at level `danger`.
- The raw `score` is never used.
- **Unverified:** this schema came from third-party documentation, not the official site.

## Outbound: Telegram (signal-only)
- `GET https://api.telegram.org/bot{token}/sendMessage` with `chat_id`, `text` (HTML-escaped,
  labelled `[SIGNAL ONLY | PAPER]`, capped at 4096 characters), `parse_mode=HTML`.
- 429 honours `parameters.retry_after`. 5xx and timeouts retry. Other 4xx do not retry.
- Not exercised against the real API in this build.

## Chain ports (Stage 9)
- `QuotePort.quote(input_mint, output_mint, in_amount) -> Quote`
- `TransactionBuilderPort.build(quote) -> PlannedTransaction` (must not sign)
- `RpcPort.simulate(plan) -> SimulationResult`; `send(signed) -> signature` (reachable only
  through an approved signer); `signature_status(sig)` returns NOT_FOUND, PROCESSED, CONFIRMED,
  FINALIZED, or FAILED; `token_balance(owner, mint)`.
- `TransactionSigner.sign(plan) -> SignedTransaction`. Production: `DisabledSigner` only.

Attempt states: VALIDATED, SIMULATED, REJECTED, SUBMITTED, CONFIRMED, FAILED, UNKNOWN, DROPPED.
Modes: VALIDATE_ONLY, SIMULATE_ONLY, BROADCAST (refused in production).
UNKNOWN means the send outcome or the landing is not known yet. It is never resubmitted.
DROPPED is set only after the plan's expiry passes with no signature found.

## Internal events
- `SignalGenerated` payload: `signal_id`, `token_id`, `entry`, `stop_loss`, `take_profit`,
  `confidence`, `label` (`SIGNAL_ONLY`). Delivered at least once.

## Reject reason codes
Signals: SAFETY_UNAVAILABLE, MARKET_UNAVAILABLE, EMPTY_MARKET, STALE_MARKET, RUGGED,
RISK_TOO_HIGH, LOW_LIQUIDITY, LOW_SCORE, INSUFFICIENT_HISTORY, NO_VOLATILITY, LOW_RISK_REWARD,
INVALID_LEVELS.
Risk decisions: EMERGENCY_STOP, STALE_PORTFOLIO, INVALID_EQUITY, DRAWDOWN_LIMIT, COOLDOWN,
MAX_POSITIONS, SPREAD_TOO_WIDE, SLIPPAGE_TOO_HIGH, ZERO_STOP_DISTANCE, RISK_LIMIT,
EXPOSURE_LIMIT, EXPOSURE_RESERVATION_DENIED, SIGNAL_NOT_ACCEPTED.
Chain: ROUTE_PROVIDER_NOT_ALLOWED, WRONG_MINT, AMOUNT_MISMATCH, QUOTE_STALE,
PRICE_IMPACT_TOO_HIGH, QUOTE_UNAVAILABLE, UNKNOWN_PROGRAM, FEE_PAYER_NOT_OWNER, FOREIGN_SOURCE,
UNKNOWN_DESTINATION, TRANSFER_TOTAL_MISMATCH, PLAN_EXPIRED, PLAN_PROVIDER_MISMATCH,
INSUFFICIENT_BALANCE, SIMULATION_FAILED, RPC_UNAVAILABLE, BROADCAST_DISABLED, SIGNER_DISABLED,
SEND_OUTCOME_UNKNOWN, ON_CHAIN_FAILURE, EXPIRED_WITHOUT_LANDING, PENDING.

## v0.2.0 adapters (read-only unless stated)
- Birdeye: GET https://public-api.birdeye.so/defi/token_overview?address=... with X-API-KEY and x-chain.
- Solana Tracker: GET https://data.solanatracker.io/tokens/{mint}/holders with x-api-key.
- Jupiter: GET https://api.jup.ag/swap/v1/quote with x-api-key, swapMode=ExactIn. Quote only.
- Jito: POST https://mainnet.block-engine.jito.wtf/api/v1/bundles (getTipAccounts) and
  GET https://bundles.jito.wtf/api/v1/bundles/tip_floor. No submit method exists.
- Helius: POST https://mainnet.helius-rpc.com/?api-key=... (getTokenAccountsByOwner,
  getSignatureStatuses). send() always refuses; simulate() refuses without a signed transaction.
- AI: POST https://api.anthropic.com/v1/messages, https://api.openai.com/v1/chat/completions,
  https://api.x.ai/v1/chat/completions. The reply must be a JSON object with decision, confidence,
  reason. Anything else is SKIP.
