# Change Ledger — Helius Sybil Cache and Request Budget

## Scope
- Add a per-`SybilAdapter` rolling 60-second request budget for every Helius JSON-RPC call.
- Fail the affected holder observation as unavailable when the configured budget is exhausted; do not retry or sleep inside the adapter.
- Add bounded concurrent holder lookups (default maximum: four holders at once).
- Cache only determinate per-wallet observations (`SELF` and `FUNDED`) for a bounded TTL (default: 300 seconds).
- Coalesce concurrent lookups for the same wallet within one adapter instance.
- Keep provider errors, malformed results, empty history, and budget exhaustion out of the cache.
- Preserve the existing scanner behavior: incomplete Sybil evidence remains WATCH/unavailable; only an explicit available cluster verdict is a positive cluster result.

## Defaults
- Helius RPC calls: maximum 30 per rolling 60-second window per adapter instance.
- Concurrent wallet-history lookups: maximum 4.
- Determinate wallet evidence cache TTL: 300 seconds.
- Constructor values are injectable for tests and can be tuned by a future configuration change.

## Safety boundaries
- Cache keys are wallet addresses; token mint is not part of the key because the lookup concerns the wallet's historical funding evidence.
- Only successful, determinate `SELF`/`FUNDED` observations are cached. Unknown/unavailable results are never cached.
- A cached observation expires after its TTL; expired or clock-inconsistent entries are discarded.
- Budget exhaustion is not a clear result and cannot approve a token.
- The shared first-funder heuristic remains an imperfect signal, not proof of coordinated malicious behavior.
- No strategy thresholds, risk limits, signing, transaction construction, broadcasting, or live execution are changed.

## Tests added
- Determinate cache hit and TTL expiry.
- Unavailable observations are not cached.
- Concurrent duplicate wallet lookups are coalesced.
- RPC request budget denies excess calls without retrying or sleeping, and replenishes after the rolling window.

## Validation status
- Tests were added but have not been executed in this environment.
- GitHub Actions are intentionally not used as a validation signal for this change because the repository's Actions billing limit was previously reported by the owner.
- No test, CI, or production-readiness pass is claimed.
