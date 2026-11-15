# Change Ledger — P4 Jupiter Price Evidence Gateway

## Change identity
- PR: #46
- Branch: `feat/p4-jupiter-price-evidence-gateway`
- Base branch: `main`
- Base SHA: `29b288a54b305eb60590467647e566fa46e48b91` (PR #45 merge commit; confirm actual branch base in PR metadata)
- Objective: produce source-attributed, slot-fresh USD-to-quote-mint price evidence.

## Files
- `bangzen_prime/infrastructure/adapters/market_data/jupiter_price.py`
- `tests/unit/test_jupiter_price_evidence.py`
- `docs/JUPITER_PRICE_EVIDENCE.md`
- `docs/CHANGE_LEDGER_P4_JUPITER_PRICE_EVIDENCE.md`

## Invariants
- No strategy thresholds, risk limits, AI authority, order sizing, or execution permissions changed.
- The adapter is read-only and never requests a swap transaction.
- Both exact mint addresses must be present; symbol matching is forbidden.
- Both prices must have positive finite USD values and liquidity, and fresh block slots.
- Mint decimals are not accepted from this provider; PR #45 finalized mint metadata remains authoritative.
- Missing/stale/invalid observations fail closed.
- Price API values are reference prices, not guaranteed execution prices.

## Validation
- Unit tests authored; NOT RUN in this authoring environment.
- `python3 tools/ci.py`: BLOCKED / NOT RUN until checked in the PR branch.
- GitHub Actions status: pending/unknown at PR creation; no green claim.
- No test pass or production readiness claim.

## Known limitations
- One provider; no independent cross-provider consensus.
- Provider liquidity is recorded but no liquidity floor is imposed by this adapter.
- Slot freshness policy must be configured by composition root and current slot must come from a trusted RPC.
- Price API V3 is heuristic reference pricing; swap quote and actual fills remain separate.
- `VerifiedQuotePrice.slot` stores the target token slot; the quote token slot is retained on
  `JupiterPriceObservation` for auditing.

## Rollback
Revert PR #46. No database migration or persistent side effect.
