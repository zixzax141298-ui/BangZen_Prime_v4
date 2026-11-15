# Change Ledger — AI Commander Sybil Evidence Gate

## Scope
- Require an explicit, non-empty `audit_data["top_holders"]` list before the AI Commander proceeds.
- Call the injected Sybil adapter before the honeypot check and before the AI brain.
- Block the Commander recommendation path when the Sybil provider raises, evidence is unavailable, the result is inconclusive, or a shared-funder cluster is positively detected.
- Permit the advisory AI call only when Sybil evidence is available and explicitly reports `is_bundled=False`, followed by the existing explicit-safe honeypot gate.

## Reason codes
- `sybil_holder_evidence_unavailable`
- `sybil_check_unavailable`
- `sybil_cluster_detected`
- `sybil_check_not_cleared`

## Safety boundaries
- The Sybil result is a shared-funder heuristic, not proof of malicious coordination. It must not be presented as certainty outside this gate.
- This change only gates calls made through `AICommander.execute`. It does not claim that the main `ScanMarketUseCase` invokes AICommander or that the ordinary scanner is now Sybil-protected.
- The current holder-profile adapter exposes concentration metrics, not verified wallet addresses. Callers must supply the top-holder address list explicitly; missing addresses fail closed.
- No scoring thresholds, risk limits, strategy weights, live execution, signing, or broadcasting are changed.

## Tests
- Added unit coverage for missing holder evidence, unavailable results, confirmed clusters, provider exceptions, and explicit-clear continuation.
- Tests have not been executed in this environment. No test or CI pass is claimed.
