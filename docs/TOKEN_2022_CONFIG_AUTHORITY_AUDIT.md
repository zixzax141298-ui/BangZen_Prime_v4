# Token-2022 Configuration and Authority Audit

## Scope

PR #48 builds on the read-only mint/TLV evidence reader introduced in PR #47.
It decodes selected fixed-width Token-2022 mint extension values into typed,
source-attributed evidence. It does not produce a token safety score or execution
authorization.

## Configurations decoded

| Extension | Configuration fields |
|---|---|
| TransferFeeConfig | Config authority, withdraw authority, withheld amount, older/newer fee epoch, max fee, basis points |
| MintCloseAuthority | Optional close authority |
| DefaultAccountState | New token-account state |
| NonTransferable | Presence flag |
| InterestBearingConfig | Rate authority, timestamps, previous/current rates |
| PermanentDelegate | Optional permanent delegate |
| TransferHook | Update authority and hook program ID |
| MetadataPointer / GroupPointer / GroupMemberPointer | Authority and target address |
| ScaledUiAmount | Authority, current multiplier, effective timestamp, next multiplier |
| Pausable | Pause authority and paused state |
| PermissionedBurn | Burn authority |

Public keys are decoded from the 32-byte OptionalNonZeroPubkey representation;
all-zero bytes mean no authority/address. Transfer fee schedules are reported
separately as older and newer, and a non-zero basis-point schedule is surfaced as
TRANSFER_FEE_NONZERO. This reader does not choose the active schedule because
current epoch evidence is not part of this call.

## Fail-closed semantics

- VERIFIED: all TLV entries were structurally valid and every present extension
  was decoded by this version's fixed-layout decoder.
- PARTIAL: an extension type is known to the catalog but its configuration layout
  is not yet decoded. Its ID is returned in unsupported_extension_ids.
- REJECTED: invalid length, malformed enum/boolean, invalid fee basis points,
  duplicate TLV type, account-only extension in mint data, or truncated TLV.
- Empty extension region remains PARTIAL when the account is an extended mint.

A known extension's presence is not enough for VERIFIED configuration evidence.
Unsupported confidential and variable-length metadata/group layouts stay PARTIAL.

## Risk observations

The decoder surfaces facts such as a configured permanent delegate, a mutable
transfer-hook program, a non-zero transfer fee, frozen default account state,
paused transfers, non-zero transfer-fee schedules, and active configuration
authorities. These are observations,
not probabilities or numeric scores. No arbitrary fee-risk threshold is imposed
here; deterministic Risk/Safety policy must consume exact basis points, maximum
fee, authorities, and evidence freshness in a later integration.

Transfer fee data contains both older and newer epoch schedules. The active fee
must be selected only when trustworthy current-epoch evidence is available.
Do not treat the newer schedule as active unconditionally.

## Source and behavior

The byte layouts follow SPL Token-2022 interface POD structures and Solana's
published extension documentation. TransferFeeConfig carries both fee authorities
and both schedules. Transfer Hook invokes a configured custom program on transfers.
Permanent Delegate has mint-wide transfer/burn authority. Pausable exposes the
pause authority and current paused state.

## Boundaries

- Helius getAccountInfo remains read-only.
- No wallet, private key, signer, transaction builder, Jupiter execution, Jito
  submission, broadcast, BUY/SELL decision, or Risk/Safety policy mutation.
- No live trading activation.
- Not yet integrated into discovery, lifecycle routing, or the deterministic
  Risk/Safety veto path.
- Confidential transfer, confidential fee, confidential mint-burn, token metadata,
  token group, and token group member values remain unsupported and PARTIAL until
  their layouts receive dedicated fixtures and review.

## Tests

Mocked unit tests cover authority decoding, transfer-fee schedule parsing, hook
program ID, pausable state, default frozen state, interest rate fields, scaled UI
multipliers, permissioned burn, unsupported extensions, malformed lengths, fee
bounds, duplicate types, and account-only extensions. No network access is used.
