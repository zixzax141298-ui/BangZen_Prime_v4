# Change Ledger — PR #42: quote decimal and fee normalization

## Repository refs
- Base branch: `feat/p3-jupiter-v2-cost-aware-quotes` (PR #41, intentionally unmerged)
- Head branch: `feat/p3-quote-decimal-fee-normalization`
- Base SHA and final head SHA: record after branch compare / final commit inspection.

## Intended changes
- Add pure Decimal normalization for Jupiter V2 raw input/output/platform-fee amounts.
- Require exact-mint, source-attributed, fresh, VERIFIED mint-decimal evidence.
- Require exact-mint-pair, source-attributed, fresh, VERIFIED price evidence for non-identity
  conversion into a common quote currency.
- Map only an explicit platform fee amount to ENTRY or EXIT cost; never derive fee amount
  from feeBps or silently treat absent fee as zero.
- Add unit tests, accounting documentation, and Change Ledger.

## Explicit exclusions
- No RPC/HTTP/provider implementation, pricing feed, persistence, AI policy, risk threshold,
  position sizing, wallet, signing, Jupiter /execute, Jito submission, or live broadcast.
- No invented decimals, prices, costs, or missing-data defaults.

## Validation
- Tests authored; NOT RUN in authoring environment unless separately recorded.
- `python3 tools/ci.py`: BLOCKED / NOT RUN unless present and actually executed.
- No claim of CI green or production readiness.

## Dependency
- PR #42 is stacked on PR #41. Merge order, after successful validation and owner approval:
  PR #41 first, then PR #42.
