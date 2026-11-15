# Adaptive token lifecycle and market sentiment

## Intent

BANGZEN must keep newly discovered candidates observable while evaluating them against
the evidence normally available at their current phase. A phase label is context, not a
BUY/SELL command. This change does not require a token to have 100% locked liquidity.

## Phase model

The current phase classifier uses DexScreener `pairCreatedAt` when present:

| Phase | Pair age | Suggested refresh |
|---|---:|---:|
| UNKNOWN | Timestamp absent/invalid | 60 seconds |
| LAUNCH | 0–1 hour | 15 seconds |
| EARLY | 1–24 hours | 60 seconds |
| GROWTH | 1–7 days | 5 minutes |
| MATURE | Over 7 days | 15 minutes |
| CEX_LISTED | Only after independently verified listing evidence | 1 hour |

The suggested refresh is a policy hint; current continuous discovery still uses its own
retry/deduplication window. Pair age is not the same as token mint age and can be missing.
A CEX stage is not inferred from a ticker, website, or social post.

## Phase-aware assessment

- Scan results use `WATCH` for missing pair/market/safety evidence, stale snapshots,
  insufficient price history, or unavailable/invalid AI responses. These candidates are
  retried; they are not treated as confirmed bad tokens. Confirmed risk gates remain
  `REJECTED`.
- UNKNOWN/LAUNCH/EARLY reduce the weight of absolute liquidity and give more weight to
  observed volume, safety, and momentum. Missing pair age is uncertainty, not proof that
  a token is mature; low liquidity alone is not a hard rejection in these phases.
- GROWTH/MATURE retain the conservative liquidity weight and configured liquidity floor.
- Safety evidence remains a separate gate. Confirmed rugged state and excessive risk are
  not waived by phase.
- Scores are ranking heuristics, not probabilities or profit forecasts.
- Insufficient price history still prevents a technical signal; it should trigger
  re-evaluation, not a permanent token blacklist. The scan result is `WATCH` until
  enough price samples exist for the technical signal.

## API call plan and cost control

1. Discovery uses DexScreener latest token profiles to create candidates.
2. Fetch pair/market data for candidates. Parse `pairCreatedAt` when available.
3. Run RugCheck safety for candidates with a usable pair.
4. Fetch holder concentration only when the AI gate is enabled and the candidate has
   reached the AI assessment step. Holder profiles are cached in-process for 5 minutes.
5. Fetch LunarCrush Solana macro sentiment only at the AI assessment step. Successful
   responses are cached for 5 minutes; the adapter is locally rate-limited to 10 requests
   per minute and rejects snapshots older than 15 minutes.
6. AI receives phase, token market evidence, holder evidence, and optional macro sentiment.
   Identical evidence prompts reuse a validated model decision for up to 30 seconds.
   If sentiment is missing, the field is UNKNOWN and does not reject the candidate.

API keys are optional and remain environment-only. LunarCrush uses
`BANGZEN_LUNARCRUSH_API_KEY`. No secret is logged or placed in URLs. The 10 rpm local
limit is a conservative guard, not a claim about every LunarCrush plan; actual plan quota
must be checked against the account. The adapter currently fetches the Solana ecosystem
topic only. It does not match memecoins by ticker because ticker collisions could attach
another asset's sentiment to the wrong mint.

## Streaming

The current WebSocket adapter still needs a watchlist-scoped subscription implementation.
Do not enable a global `logsSubscribe: all` stream for production monitoring: it can create
large data/credit consumption and unnecessary message processing. The next streaming
increment should subscribe only to selected token/program accounts, reconnect with bounded
backoff, deduplicate signatures, and fall back to periodic HTTP snapshots. Helius
`transactionSubscribe` is plan-dependent; standard `logsSubscribe` supports a single
mentioned pubkey per subscription. Streaming is not enabled by this PR.

## Known limitations

- Phase uses pair creation time, not original mint creation time.
- Lifecycle state and phase history are not yet persisted across restarts.
- CEX listing verification and token-specific social sentiment are not implemented.
- Macro sentiment is broad Solana ecosystem context, not a token-specific signal.
- Pair-age refresh intervals are documented policy hints; adaptive per-token scheduling
  and WebSocket orchestration are future work.
- Live trading remains locked. This PR changes discovery/scoring context only.
