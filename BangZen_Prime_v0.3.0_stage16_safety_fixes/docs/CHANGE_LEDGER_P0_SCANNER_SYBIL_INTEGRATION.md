# Change Ledger — Scanner Sybil Evidence Integration

## Scope
- Extend the Solana Tracker holder profile with validated wallet addresses extracted only from recognized account fields: `owner`, `address`, or `wallet`.
- Rank extracted addresses by reported token amount and retain at most 20 in the cached holder profile.
- Wire the Helius-backed Sybil adapter into the normal `ScanMarketUseCase` composition path.
- Run the Sybil gate after market/RugCheck/holder retrieval and before AI scoring.
- Submit at most the five largest-holder addresses to the Sybil adapter to bound RPC work.
- Keep candidates in WATCH when holder addresses are missing, the provider is unavailable, or the result is inconclusive; reject a candidate only when the adapter reports an available positive shared-funder cluster.

## Reason codes
- `SYBIL_UNAVAILABLE`
- `SYBIL_CLUSTER_DETECTED`

## Safety and limitations
- Provider account-address field names are not verified by the repository's existing adapter documentation. Only recognized string fields that pass Solana address validation are used; missing/unknown fields produce no usable Sybil evidence and fail closed.
- A shared first-funder heuristic is not proof of malicious coordination. A clear result is limited to the five largest holders sampled by this scan.
- The Sybil adapter currently performs up to two Helius RPC calls per submitted holder. This is bounded to five holders per candidate but still has API quota/latency cost; provider-level rate limiting and caching remain follow-up work.
- The normal scanner now uses the gate when built through the standard composition root. The AI Commander retains its own independent gate.
- No scoring thresholds, risk limits, strategy weights, live execution, signing, or broadcasting are changed.

## Tests
- Added end-to-end scanner cases for unavailable Sybil evidence, missing wallet addresses, and detected clusters.
- Tests have not been executed in this environment. No test or CI pass is claimed.
