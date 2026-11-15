# Token-2022 Deterministic Risk Veto

## Purpose

Consume PR #47/#48 validated mint-extension evidence inside the deterministic
risk boundary. The result is an eligibility gate, not a profitability score or
an order authorization.

## Outcomes

- **BLOCKED**: exact mint mismatch, rejected evidence, or hard transfer-state veto.
- **HOLD**: missing, stale, future-dated, partial, unavailable, or unsupported
  configuration; or a feature requiring additional review/cost modelling.
- **APPROVED**: only exact-mint, fresh, VERIFIED evidence with VERIFIED decoded
  configuration and no recognized veto/review flags.

Hard veto flags: paused transfers, non-transferable mint, frozen default accounts,
and uninitialized default account state. Review flags include transfer fees,
permanent delegate, transfer hook, and active authorities. These features are not
labelled malicious; they require further validation before entry.

The evidence age bound is inherited from the existing RiskLimits
max_portfolio_age value. No new numeric threshold is introduced.

## Boundaries

- No network calls, provider credentials, wallet access, signing, transaction
  construction, Jupiter execution, Jito submission, or broadcast.
- AI cannot override this result. APPROVED means only that this specific
  Token-2022 extension gate found no known blocker; all other Risk/Safety gates
  still apply.
- Classic SPL Token requests retain their existing path. Token-2022 requests
  must provide matching extension evidence; otherwise they HOLD.

## Rollback

Revert this PR. No schema migration or persistent side effect.
