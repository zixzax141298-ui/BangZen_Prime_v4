# Jupiter Price Evidence Gateway

## Purpose
PR #46 adds a read-only adapter for Jupiter Price API V3. It retrieves USD price
observations for both the target mint and the requested quote mint, then derives
one target-token price in quote-token units using Decimal arithmetic.

## Data contract
- Request: `GET https://api.jup.ag/price/v3?ids=<target>,<quote>`
- Authentication: `x-api-key` injected by the composition root; never logged.
- Identity: exact mint addresses are the keys in the provider response.
- Required per mint: positive finite `usdPrice`, positive finite `liquidity`,
  and non-negative integer `blockId`.
- Freshness: each `blockId` is compared with an injected current Solana slot.
  `max_slot_lag` is mandatory policy configuration; no silent threshold is selected.
- Conversion: `target_usdPrice / quote_usdPrice`, using Decimal arithmetic.
- Mint decimals from this API are ignored. PR #45 finalized account metadata remains
  the source of verified decimals.

## Important interpretation
Jupiter Price API V3 is a reference price based on recent on-chain swap activity and
provider heuristics. It is not an amount-specific execution quote and does not guarantee
a fill price. Use Jupiter Swap API V2 quote/order data for execution economics and
reconcile actual fills independently. The provider's `createdAt` field is not used as
price-observation time; freshness is established through `blockId` versus current slot.
Missing target/quote mint, stale/future slot, malformed or non-positive values fail closed.

## Security and boundaries
- Read-only HTTP GET only; no wallet, transaction, signer, swap execute, Jito, or broadcast.
- No API key in URL, logs, exception messages, or evidence output.
- No fallback to DexScreener USD prices and no substitution by symbol.
- A valid price is not a token-safety verdict and cannot bypass Risk/Safety.
- Provider liquidity is recorded as evidence, not treated as an approved liquidity threshold.
- Caller controls timeout, retry, rate limit, circuit breaker and slot freshness policy.

## Tests
Mocked tests cover conversion, exact mint lookup, missing data, malformed numbers,
liquidity, stale/future slots, invalid slots, configuration, and secret non-disclosure.
No network calls are made by unit tests.
