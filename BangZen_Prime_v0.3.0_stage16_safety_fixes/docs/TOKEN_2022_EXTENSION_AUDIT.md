# Token-2022 Extension Risk Evidence

## Purpose

PR #47 adds a read-only Helius getAccountInfo reader and a pure TLV parser for
Token-2022 mint extensions. It closes the gap left by PR #45, whose mint metadata
reader intentionally validates only the base mint layout and does not decode TLV.

## What is validated

- Exact 32-byte base58 mint address before RPC.
- RPC context slot, account existence, exact Token-2022 owner program, and
  executable=false.
- Base mint initialized flag and the extended-mint padding/account-type marker.
- TLV header boundaries, u16 little-endian type and length, duplicate types,
  account-only extension IDs appearing in mint data, and values extending beyond
  account data.
- Known extension discriminants are mapped using Solana's published
  ExtensionType catalog (catalog snapshot: 2026-11-13).
- Unknown future extension IDs return PARTIAL and
  UNKNOWN_EXTENSION_PRESENT; they are never ignored or treated as safe.

## Extension families surfaced

The catalog detects transfer-fee configuration, mint-close authority, confidential
transfer and confidential fee extensions, default account state, non-transferable,
interest-bearing configuration, permanent delegate, transfer hook, metadata and
group pointers/metadata, confidential mint-burn, scaled UI amount, and pausable.

Each observation includes a deterministic source_record_id derived from mint, RPC
slot, and account-data length, plus source and observed_at provenance.

The evidence emits presence flags only. It does not deserialize extension-specific
authority keys, fee values, hook program code, or runtime behavior. A follow-up
capability must decode and evaluate those fields against explicit policies before
any strategy or Risk/Safety consumer can treat them as resolved.

## Status semantics

- VERIFIED: TLV framing is structurally valid and every type ID is known in the
  pinned catalog. This is not a safety verdict.
- PARTIAL: the TLV region is empty/ambiguous or contains an unknown extension ID.
- UNAVAILABLE: account is missing.
- REJECTED: account owner/layout is incompatible or TLV is structurally invalid.

A Token-2022 mint with the base 82-byte layout and no extensions is represented as
verified with NO_EXTENSIONS_PRESENT. An extended mint with an empty TLV region
remains partial because the allocation cannot be fully explained.

## Risk flags (not an automatic score)

- TRANSFER_FEE_CONFIG_PRESENT: transfers may incur configurable fees.
- TRANSFER_HOOK_PRESENT: transfers invoke custom program logic; hook program
  validation and simulation are separate work.
- PERMANENT_DELEGATE_PRESENT: a privileged delegate may transfer or burn tokens.
- DEFAULT_ACCOUNT_STATE_PRESENT / PAUSABLE_PRESENT: account/transfer state may
  be administratively constrained.
- NON_TRANSFERABLE: ordinary transfers are disabled; this is incompatible with
  normal buy-and-sell assumptions.
- Confidential, interest-bearing, scaled-amount, mint-close, and metadata/group
  extensions are surfaced for specialized review.

No extension flag alone is translated to a numeric risk score, BUY/SELL instruction,
or automatic execution veto in this PR. Downstream deterministic Risk/Safety must
own the policy decision and fail closed when evidence is missing or partial.

## Boundaries

- Read-only getAccountInfo only; no new credentials, wallet, signer, transaction
  builder, Jupiter execution, Jito submission, or broadcast.
- No change to strategy thresholds, scoring weights, AI authority, or execution mode.
- The reader is not yet wired into the live discovery/orchestration path; integration
  is a separate PR after this capability is reviewed.
- No extension-specific values or authorities are decoded. A known extension being
  present is a fact, not a conclusion about whether its current configuration is
  malicious or benign.

## Tests

Mocked unit tests cover known/unknown IDs, TLV bounds, duplicate types, invalid
account-only extensions on mints, missing accounts, malformed base64/space, mint
layout, initialization, slot, and address validation. No external network is used.
