# Quote normalization and fee valuation

## Purpose

PR #42 adds deterministic normalization between Jupiter V2 raw amounts and human token
units, plus explicit conversion of a known platform-fee amount into one quote currency.
It is a pure domain capability; provider I/O and transaction execution are excluded.

## Evidence contracts

- Mint decimals must arrive as `VerifiedMintDecimals` with exact mint, source, observation
  time, `VERIFIED` status, and optional non-negative RPC slot.
- Price conversion must arrive as `VerifiedQuotePrice` with exact token mint, quote mint,
  positive `quote_per_token`, source, observation time, `VERIFIED` status, and optional slot.
- Evidence must be timezone-aware, not from the future, and no older than caller-supplied
  `max_age`. The caller is responsible for choosing a conservative age limit for the market.
- Same-mint conversion uses an exact identity rate of 1 and needs no external price feed.
- The module validates evidence shape/status/freshness; it does not independently fetch RPC
  accounts or prove that a caller's VERIFIED assertion is truthful. The adapter/Data Gateway
  must verify the on-chain mint owner and decode decimals before constructing that evidence.

## Arithmetic

For raw token amount (A) and mint decimals (d):

[
A_{ui} = A / 10^d
]

For token price (P) in quote-currency units per whole token:

[
V_{quote} = A_{ui} 	imes P
]

All calculations use `Decimal`; binary floats are rejected in evidence construction.
The output amount remains denominated in the output token. It is not converted to quote
currency unless a separately verified output price is added in a future change.

## Fee accounting

- Only exact `platformFee.amount` is converted into a quote-currency cost.
- `feeBps` and `platformFee.feeBps` remain metadata. The module does not derive an
  amount from basis points because the fee base/collection semantics are not assumed.
- Missing `platformFee` remains `None`, not zero. Cost conversion fails closed when no
  explicit fee amount is available.
- The normalized platform fee can be mapped to ENTRY or EXIT in
  `ExecutionCostBreakdown`; the caller must choose the correct lifecycle side.
- Do not subtract the platform fee a second time from Jupiter's quoted output amount.
- This does not calculate exit fees, slippage, price impact, priority fees, rent, failed-exit
  reserves, or Jito tips. Those remain separate evidence/cost inputs.

## Safety boundary

No HTTP/RPC, token metadata lookup, pricing API, wallet, signer, transaction builder,
Jupiter `/execute`, Jito submission, sizing, BUY/SELL decision, or broadcast is added.
A normalized quote is not a trade authorization. Missing, stale, mismatched, or
non-VERIFIED evidence raises `DomainError` and must be surfaced as UNAVAILABLE/HOLD.
