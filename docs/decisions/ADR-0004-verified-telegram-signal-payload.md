# ADR-0004: Verified Identity and Provenance in Telegram Signal Events

- Status: Proposed in PR #56
- Date: 2026-11-13
- Depends on: PR #55 mode-aware Telegram gateway

## Context

The Telegram gateway previously received an internal token UUID only. Displaying that UUID as a token address would be misleading and would prevent a user from reliably identifying the Solana asset. The validated market observation already contains the chain, base mint, symbol, pair address, DEX ID, observation time, and adapter provenance.

## Decision

Extend accepted signal events with the identity and provenance from the exact selected `PairSnapshot`. Before emitting metadata, the domain verifies that the supplied chain+mint maps to the signal token UUID and chain+pair address maps to the signal pair UUID. Partial metadata is rejected. The market observation timestamp must be timezone-aware and is normalized to UTC.

The DexScreener adapter marks the observation source as `DexScreener`. The Telegram formatter includes asset identity, pair/DEX, source, observation time, heuristic price references, score, and confidence. Legacy events without metadata explicitly show that the mint is unavailable and retain the internal UUID label; no UUID is represented as a mint.

## Safety semantics

- This is a research alert, not a buy/sell instruction or execution authorization.
- Entry, stop, and target are heuristic reference levels; they are not exchange orders or guarantees of fill.
- Heuristic confidence is not a calibrated probability of profit.
- No wallet, signer, balance, Jupiter swap, or Jito submission capability is added.

## Consequences

The event contract is richer for newly accepted signals. Old persisted outbox events remain compatible and are rendered with an explicit unavailable-mint fallback. The new `PairSnapshot.source` field defaults to `UNSPECIFIED` for other adapters until they provide explicit provenance.
