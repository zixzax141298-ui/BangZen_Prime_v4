# ADR-0002: Remove the Local Plaintext Burner Wallet

- Status: Proposed in PR #52
- Date: 2026-11-13
- Supersedes: no prior approved signer architecture
- Related policy: AI_RULES.yaml v13.0, SECURITY.md, RULES.md

## Context

The existing `BurnerWallet` generated a 32-byte seed, retained it in a Python object, exposed a method that signed arbitrary message bytes, and persisted the seed as plaintext hexadecimal JSON. File mode `0600` narrows access for other local OS users but does not encrypt the seed, protect it from malware or a compromised/rooted Android device, or isolate it from the bot process. The wallet also relied on a project-local Ed25519 implementation that has not been independently audited.

The wallet adapter was not an approved signer boundary and was not wired through the deterministic Risk/Safety and controlled execution path. Keeping it would create a parallel signing capability outside the intended architecture.

## Decision

Remove the plaintext burner wallet and its custom Ed25519 signing implementation. Remove the `BANGZEN_BURNER_PRIVATE_KEY` environment setting and the corresponding `Settings` field/parser so the application no longer accepts or retains this legacy secret. Do not replace them with another seed-loading or signing implementation in this PR.

Retain the fail-closed `WalletSigner` compatibility shim and keyless wallet diagnostics. The default remains read-only/paper-only. No key material may be loaded, stored, logged, or transmitted by BANGZEN PRIME.

## Future wallet architecture (not implemented here)

Any future funded-wallet capability must be a separately approved design and implementation. It must use an isolated signer boundary (prefer hardware-backed or external signer isolation), strict transaction intent validation, deterministic Risk/Safety veto, user-controlled authorization, durable audit records, simulation, reconciliation, and an independently tested emergency stop. The AI Manager and Telegram interface must never receive private keys or signing authority.

A local application lock cannot freeze an on-chain address or revoke a leaked key. If a key is compromised, assets must be moved to a new secure wallet.

## Consequences

- The current burner wallet cannot be used to create, load, or sign with a local keypair.
- Legacy `.env` files containing `BANGZEN_BURNER_PRIVATE_KEY` must have that line removed; the setting is now rejected as unknown.
- This is intentionally a capability removal, not a temporary feature flag.
- Wallet creation/funding and live transaction signing remain out of scope and locked.
- A future secure signer must be designed from the approved execution architecture, not re-enable this implementation.

## Validation

Tests added by PR #52 assert that the removed modules are not importable and that wallet diagnostics remain keyless. Test execution and CI results must be recorded from actual runs; code review alone is not a passing security review.
