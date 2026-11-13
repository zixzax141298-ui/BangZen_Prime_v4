# Change Ledger — P0 Independent Execution Safety Veto

## Scope
- Add a typed `SafetyApproval` result to the controlled execution boundary.
- Require a separately injected `risk_gate` before any BROADCAST path can proceed.
- Run deterministic Risk/Safety approval before the AI pre-trade gate and before quote retrieval, transaction building, simulation, signing, or RPC send.
- Fail closed if the risk gate is absent, throws, or returns an unrecognized result.
- Add integration regression tests for missing, denied, malformed, and failing risk gates.

## Security rationale
The previous BROADCAST path required an AI BUY decision but had no independent deterministic Risk/Safety veto at the execution boundary. AI approval is not risk approval. A model response must never be sufficient to authorize a transaction.

## Safety properties
- Missing Risk/Safety gate => `RISK_APPROVAL_UNAVAILABLE`.
- Denied, malformed, or exception-raising Risk/Safety gate => `RISK_APPROVAL_DENIED`.
- The risk gate executes before AI approval and before quote/build/RPC/signer operations.
- Existing production configuration remains paper-only and broadcast-disabled.
- This change does not instantiate a production risk gate, enable a signer, or enable live trading.

## Validation
- Added integration tests in `tests/integration/test_controlled_execution.py`.
- Tests have NOT been executed in this change session.
- No CI success is claimed; verify GitHub Actions before merge.

## Important limitation
This PR establishes a mandatory independent veto interface, not a complete production risk adapter. A future implementation must bind the gate to fresh portfolio balances, open exposure, daily drawdown, loss cooldown, token/liquidity constraints, fee/slippage estimates, and a persisted risk decision tied to the exact transaction intent. Until then, broadcast remains unavailable.
