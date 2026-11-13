# Jupiter Swap API V2 quote economics

## Scope

This module calls `GET https://api.jup.ag/swap/v2/order` without `taker`.
It is quote-only: the documented response has no transaction (`null` or an empty
string for quote-only/error quote cases); no transaction is signed or submitted.

The adapter validates the requested mints and raw input amount against the response,
and records the selected router, order mode, total fee rate, and top-level fee mint.
When present, `platformFee` contains the platform-fee amount and platform-fee rate;
its fee token is the top-level `feeMint`, not a nested `platformFee.feeMint` field.

## Accounting rules

- `inAmount`, `outAmount`, and `platformFee.amount` are raw token units, not quote currency.
- `feeBps` is the total fee rate; `platformFee.feeBps` is only the Jupiter platform-fee rate.
  They are not interchangeable and must not be added together.
- Top-level `feeMint` identifies the token in which swap fees are collected and also
  identifies the token denomination of `platformFee.amount`.
- The quote output already reflects applicable route/platform fee treatment. Do not subtract
  `platformFee.amount` from `outAmount` again.
- Convert raw amounts using verified mint decimals, then convert fee token value into the
  same quote currency used by `ExecutionCostBreakdown`. If decimals, fee mint conversion,
  or a required cost estimate is unavailable, mark that cost UNAVAILABLE and do not treat
  the economics as fully validated.
- The adapter intentionally does not invent gas, rent, priority-fee, slippage, price-impact,
  or Jito-tip values. Those require their own validated sources and must not be double-counted.
- A quote is a snapshot, not a fill guarantee. Refresh it before any separately authorized
  execution decision and enforce expiry/price movement in the execution layer.

## Safety boundary

No wallet, private key, signer, transaction builder, Jupiter `/execute`, Jito endpoint,
BUY/SELL decision, sizing, or broadcast is reachable from this quote adapter.
Deterministic Risk/Safety remains the final veto. A valid quote is not trade approval.
