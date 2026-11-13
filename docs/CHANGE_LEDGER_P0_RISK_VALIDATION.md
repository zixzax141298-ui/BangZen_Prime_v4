# Change Ledger — P0 Risk Configuration Validation

## Scope
- Validate every RiskLimits field at construction.
- Validate TradeRequest identifiers, mint, liquidity, spread and slippage before evaluation.
- Validate exposure reservation inputs to prevent NaN/Infinity and negative values from corrupting limits.
- Preserve zero-valued optional thresholds (minimum liquidity, drawdown, spread, slippage and fee) where meaningful.

## Safety properties
- Invalid risk configuration raises DomainError and cannot be used to approve a trade.
- Emergency-stop behavior and existing sizing/exposure policy remain unchanged.
- This change does not enable signing, transaction broadcast, wallet loading, or live trading.

## Validation
- Added unit tests for malformed limits, time boundaries, market-data values, and exposure reservation inputs.
- Tests have NOT been executed in this change session. GitHub Actions must validate the PR before merge.
- No claim of CI success is made.

## Follow-up
- Independently audit signer isolation, controlled execution authorization, transaction construction, and RPC reconciliation in subsequent PRs.
