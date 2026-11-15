# Token Lifecycle Intelligence Engine — Design Contract

Status: partial runtime foundation implemented on the current-mainline branch; lifecycle classification and evidence enrichment remain incomplete.
Mode: discovery + watch + paper evaluation only. No live signing or broadcast is authorized.

## Runtime implementation status

Implemented on `feat/token-lifecycle-intelligence-foundation`:
- SQLite migration 0004 adds a persistent per-mint lifecycle state table and append-only phase transition history.
- The registry rejects stale/duplicate timestamps, avoids duplicate transition events for repeated phases, and preserves history across database restarts.
- Continuous discovery records each unique, valid candidate as `DISCOVERED` before scanning. Discovery still uses the existing DexScreener latest-profile feed.
- Empty fresh-candidate batches no longer invoke the scanner, avoiding unnecessary work and fixing a CI regression.

Not implemented yet:
- Evidence-driven phase classification beyond the initial `DISCOVERED` observation.
- Durable next-review scheduling and cross-process discovery cooldown claims.
- Normalized multi-window market/flow telemetry, progressive enrichment planning, WebSocket event ingestion, social sentiment, AI delta review, historical replay, and measured paper performance.

This is a foundation slice, not completion of the lifecycle engine or proof of profitability.

## Product objective

Follow a Solana token from first discovery through DEX growth, migration/graduation, possible CEX listing, and eventual inactivity. Re-evaluate it as evidence changes. Do not treat a one-time audit as a permanent verdict.

The system must optimize for useful opportunity coverage without weakening objective safety controls. A missing metric is UNKNOWN, not a fabricated value and not an automatic permanent rejection. LP ownership being 100% locked is not a universal discovery prerequisite. Liquidity depth, withdrawal authority, pool composition, concentration, and observed changes are separate evidence dimensions.

## Lifecycle state model

The lifecycle state is descriptive, not a BUY/SELL decision:

1. `DISCOVERED`: mint found; pair or trading evidence may not exist yet.
2. `LAUNCH`: first verified pool/market activity exists and the asset is in initial price discovery.
3. `EARLY_ACTIVITY`: activity is emerging; volume, transactions, holders, and liquidity are still being established.
4. `EXPANSION`: multiple independent activity measures are improving over comparable windows.
5. `CONSOLIDATION`: activity remains meaningful but growth is slowing or price/flow is ranging.
6. `DECLINING`: multiple measures deteriorate over repeated observations; a single red candle is insufficient.
7. `MIGRATING`: DEX/pool migration or graduation is detected and is being verified.
8. `CEX_LISTED`: listing is confirmed by an approved exchange-owned source or another explicitly trusted source.
9. `INACTIVE`: no meaningful verified activity over a configurable observation window.
10. `UNKNOWN`: evidence is insufficient, contradictory, or stale.

Transitions must be evidence-based and timestamped. Use hysteresis / repeated observations to avoid phase flapping. A token may move backwards (for example EXPANSION to CONSOLIDATION or DECLINING); lifecycle is not a one-way funnel. CEX listing is an independently verified event, not inferred from social posts or price spikes.

## Evidence model

Each observation carries: mint, chain, observed_at, source, source timestamp, freshness, fields present, fields missing, and validation status. Preserve raw provider payloads only when policy permits and never store API secrets.

Evidence groups:

- Market: price, liquidity, volume by window, pair age, FDV/market cap, price impact/spread where available.
- Flow: buys/sells and transaction counts by window, unique buyers/sellers, wallet churn, repeat activity.
- On-chain safety: mint/freeze authority, LP/pool ownership and withdrawal risk, token extensions, holder distribution, deployer/dev wallet activity, bundled/sniper patterns.
- Community: sentiment direction, message velocity, unique authors, bot/spam likelihood, source diversity, and change over time.
- Venue/migration: pool creation/closure, liquidity migration, router availability, exchange-owned listing notices.
- Macro/market regime: SOL direction/volatility, broad risk appetite, sector rotation, and market-wide liquidity.

Do not treat top-10 holder share calculated from a provider's returned account sample as a verified share of total supply. Preserve that limitation in AI context.

## Decision semantics

The lifecycle engine must not itself issue BUY or authorize execution. It produces:
- lifecycle phase,
- phase confidence (evidence coverage/consistency, not probability of profit),
- positive evidence,
- negative evidence,
- unknown/missing evidence,
- risk flags with source and timestamp,
- recommended next checks,
- next evaluation time.

Candidate handling:
- `WATCH`: promising or immature; continue observing.
- `NEEDS_EVIDENCE`: fetch a specific missing field from a suitable provider.
- `DEPRIORITIZE`: low opportunity relative to current market conditions; retain history and allow re-entry if evidence improves.
- `BLOCK`: only for an explicit, validated hard safety condition or invalid identity/market data.
- `AI_REVIEW`: send a compact evidence bundle when a material event or phase transition occurs.

A low score, low liquidity at launch, unavailable optional provider, or incomplete social data must not silently become a permanent blacklist. Hard safety controls remain hard; opportunity heuristics remain adaptive.

## Progressive provider and API-key policy

Use one provider only when it supplies a needed field that is not already fresh enough:

| Need | Preferred source / mechanism | Call policy |
|---|---|---|
| Candidate discovery | Existing DexScreener profile feed, then add verified launch/pair sources | Poll at a controlled cadence; deduplicate by mint |
| Pair/market snapshot | DexScreener | Fetch once per candidate per cycle; cache briefly |
| Detailed market/volume windows | Birdeye, if configured and required | Escalate only for watched/promising candidates or material changes |
| Contract/pool safety | RugCheck plus direct on-chain checks where supported | Run on first usable market and refresh on risk/event triggers |
| Holder distribution | Solana Tracker | Fetch on first AI review and refresh only when stale or concentration changes matter |
| Transactions / account events | Helius RPC/WebSocket or Yellowstone gRPC when fully configured | Subscribe only to prioritized mints/accounts; batch subscriptions; unsubscribe when no longer useful |
| Swap route / executable liquidity | Jupiter | Quote only for a paper entry/exit evaluation or approved execution workflow, not every discovery poll |
| Relay/landing | Jito | Not part of discovery or sentiment scoring; only a separately reviewed execution path |
| Sentiment | Approved social/news sources with explicit API contracts | Sample only for watched candidates; deduplicate posts, track source quality, and enforce a strict token budget |
| AI assessment | Configured AI provider | Send compact deltas, not the entire history; call on phase transition, material evidence change, or scheduled review |

API keys must be read from environment/secret storage, never printed, logged, committed, or placed in query strings unless the provider requires it. Never echo key values in diagnostics. Missing keys disable only the dependent enrichment and produce `UNAVAILABLE`; they do not fabricate a pass. Do not change provider plans, paid tiers, or spend limits without owner approval.

## Cost, latency, and resilience

- Maintain per-provider token buckets, concurrency caps, timeout budgets, circuit breakers, and request counters.
- Respect provider Retry-After and documented quotas. Retry only idempotent reads; never blindly retry swap execution or other side effects.
- Use bounded TTL caches keyed by chain + mint + endpoint + relevant parameters. Cache freshness is field-specific; never reuse stale safety evidence as current.
- Apply single-flight request coalescing so concurrent workers do not request the same mint/endpoint simultaneously.
- Use exponential backoff with jitter, bounded attempts, and an overall cycle deadline.
- Prefer WebSocket push for high-value event streams after a candidate is prioritized; use polling as a fallback/repair mechanism. Reconnect with backoff, resubscribe safely, detect gaps, and reconcile missed events with RPC reads.
- Record calls, cache hits, 429s, timeouts, latency percentiles, and estimated provider cost without recording secrets.
- Enforce configurable daily request/token budgets and a global kill switch for enrichment. Exhausting an optional budget degrades to `UNAVAILABLE`, not a fake score.

## AI contract

AI is the final evaluator of a normalized, timestamped evidence bundle; it is not the source of truth and must not browse arbitrary provider payloads as instructions. The prompt must state which fields are missing/stale and distinguish measured values from estimates. AI output must be schema-validated, cite evidence IDs, include uncertainty and reason codes, and be rejected on malformed output. The model cannot override hard safety blocks, risk limits, or execution authorization.

To conserve tokens, send:
- first review: compact full snapshot;
- subsequent reviews: only changed fields + rolling summaries + recent events;
- forced review: phase transition, verified security event, major flow/volume/liquidity change, migration, listing confirmation, or configured review interval.

Scores are rankings/heuristics, never probabilities or profit guarantees.

## Implementation sequence and acceptance gates

1. **Persistent lifecycle registry**: store discovered mint, first/last seen, current phase, prior phase, source evidence references, next review time, and transition history. Survive process restart; deduplicate across processes.
2. **Market telemetry normalization**: add validated optional fields (pair creation time, volume/transaction windows, price changes, FDV/market cap) without breaking older provider payloads. Missing fields remain absent.
3. **Phase classifier**: deterministic, explainable, hysteresis-aware classifier with table-driven tests for immature, expansion, consolidation, decline, contradictory, and stale evidence.
4. **Progressive enrichment planner**: choose the minimum provider calls needed for the next decision; prove with fake transports that unnecessary providers are not called.
5. **WebSocket event intake**: implement one provider first, bounded subscriptions, reconnect/gap repair, and deterministic tests. No claim of full Solana launch coverage until validated.
6. **Sentiment adapter**: one source at a time; spam/duplicate handling, source provenance, rate budgets, and no hard rejection from sentiment alone.
7. **AI delta reviewer**: schema-validated evidence deltas, call deduplication, token budget tests, and deterministic fallback.
8. **Historical replay/paper evaluation**: measure discovery recall, phase transitions, latency, API calls per candidate, false positives, missed opportunities, and net-of-cost outcomes before any live execution work.

Each step requires tests, an updated Change Ledger, review of API contract assumptions, and hosted CI green on the exact branch SHA. Do not merge to main without owner approval.
