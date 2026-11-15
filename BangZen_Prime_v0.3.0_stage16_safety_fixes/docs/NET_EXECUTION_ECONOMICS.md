# Net Execution Economics

## Purpose
This PR adds pure round-trip cost arithmetic. It prevents a gross-positive quote from
being mistaken for a net-profitable opportunity when fees, slippage, price impact,
priority fees, Jito tips, rent, or a failed-exit reserve consume the apparent edge.

## Cost model
Every input is expressed in the same quote currency and normalized scale:
- Entry and exit fees
- Entry and exit slippage cost
- Entry and exit price-impact cost
- Solana priority fee
- Jito tip
- Rent reserve
- Failed-exit reserve
- Other explicitly identified cost

net_pnl = expected_exit_gross - entry_notional - total_costs
break_even_exit_gross = entry_notional + total_costs
net_return_pct = net_pnl / entry_notional * 100

Expected exit value must be gross before these costs. The caller must not pass an exit
estimate that already subtracts one of the explicit cost categories. Token decimals,
SOL/USD conversion, route quote interpretation and cost estimation remain upstream
responsibilities and must be validated independently.

## Safety
- Uses Decimal-only validated values; rejects floats, booleans, negatives and non-finite values.
- Does not select tokens, set thresholds, size a position, or authorize an order.
- Does not access Jupiter, Jito, RPC, wallets, secrets, signers or network.
- Does not change RiskLimits or production configuration.
- No live execution or transaction broadcast is enabled.

## Next integration stages
1. Connect validated Jupiter quote and token-decimal metadata to produce quote-currency entry/exit estimates and cost evidence.
2. Add fee/priority-fee estimation and Jito tip-floor validation; ensure tip is only paid when route eligibility and net edge remain positive.
3. Add simulation/reconciliation integration and paper replay with actual fills, failed exits, partial fills and market impact.
4. Keep live execution separately locked behind owner-approved policy, deterministic risk veto, independent security review and emergency-stop tests.

## Validation
Unit tests are added in tests/unit/test_execution_economics.py. They were not executed
in the authoring environment. python3 tools/ci.py is absent from the inspected main
tree, so the required project gate is BLOCKED / NOT RUN.
