# Verified Solana Mint Metadata Gateway

## Purpose

PR #45 adds a read-only Helius `getAccountInfo` path that verifies the owner program,
base mint layout, initialization flag, raw supply, decimals, RPC context slot, and
observation timestamp before producing `VERIFIED` mint metadata evidence.

The reader is injected with the existing `HeliusRpc.account_info` method and a clock.
It does not access credentials, construct transactions, or make trading decisions.

## Validation rules

- Validate the requested address as a 32-byte base58 Solana address before RPC.
- Request `getAccountInfo` with `encoding=base64` and `commitment=finalized`.
- Require a non-negative RPC context slot and an account value.
- Allow only the classic SPL Token Program or Token-2022 as the account owner.
- Require `executable=false`, a base mint payload of at least 82 bytes, valid base64,
  and a `space` value consistent with decoded data when supplied.
- The classic Token Program mint layout must be exactly 82 bytes.
- A Token-2022 mint without extensions may use the 82-byte base layout. Extended mints
  must be at least 166 bytes, preserve zero padding at bytes 82..164, and carry the Mint
  account-type discriminator (1) at byte 165. Token-account discriminator (2), truncated
  extended layouts, and the 355-byte multisig layout are rejected. The reader decodes only
  the common 82-byte base mint fields and reports trailing bytes after offset 165 without
  interpreting their TLV contents.
- Decode supply from bytes 36..43, decimals from byte 44, and initialized from byte 45.
- An uninitialized mint is `REJECTED`; a missing account is `UNAVAILABLE`; malformed
  provider data raises a non-retryable adapter error. None of these states expose usable
  decimals.
- Only a verified result can be converted to the existing `VerifiedMintDecimals` quote
  evidence consumed by PR #42.

## Token-2022 limitation

This PR does **not** decode or audit Token-2022 TLV extensions. The reported trailing-data byte count is informational only; it is not a decoded TLV extension length. Transfer fees, transfer hooks, permanent delegates,
default account state, confidential transfer, metadata pointers, and other extensions
remain outside this gateway's scope and must be checked by a separate token-safety
capability before any future live execution. `VERIFIED` here means only that the base
mint metadata was read from an allowlisted owner program and passed the stated checks;
it is not a token safety verdict.

## Freshness and provenance

Each observation carries the requested mint, source, finalized RPC slot, and timezone-aware
observation time. The consumer must apply its own freshness policy before using the
decimals evidence. A slot is a chain context marker, not a wall-clock timestamp.

## Safety boundary

- Read-only `getAccountInfo` only.
- No price feed is added; quote-price evidence remains a separate future gateway.
- No AI direct RPC access, wallet, private key, signing, BUY/SELL, sizing, Jupiter
  `/execute`, Jito submission, or broadcast.
- Risk/Safety remains deterministic and retains final veto.
- Missing, malformed, unsupported, or uninitialized metadata must never be coerced to
  zero decimals or treated as a successful check.
