# Change Ledger — Sybil Unknown Semantics and Commander Honeypot Gate

## Scope
- Represent inconclusive Sybil/funder evidence as `is_bundled=None` and `available=False`.
- Report `is_bundled=True` only when at least three holders are positively observed sharing a funder.
- Report `is_bundled=False` only when the holder sample is sufficiently large and all lookups completed without a confirmed cluster.
- Prevent AICommander from calling the AI brain unless the honeypot provider completed and explicitly returned a safe result.

## Safety
- Missing, partial, malformed, or unavailable honeypot evidence blocks the Commander recommendation path.
- Sybil uncertainty is not mislabeled as a confirmed cluster or a clean result.
- This change does not wire Sybil into ScanMarketUseCase or claim full end-to-end Sybil coverage.
- No live execution, signing, or broadcasting is enabled.

## Tests
- Added tests for confirmed Sybil clusters, incomplete funder evidence, insufficient holder samples, and Commander honeypot fail-closed behavior.
- Tests have not been executed in this environment. No CI or test pass is claimed.
