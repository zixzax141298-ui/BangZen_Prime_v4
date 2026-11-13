# Change Ledger — P0 Legacy Signer Lock

## Scope
- Disable the legacy `WalletSigner` adapter that accepted a base58 private key and signed arbitrary serialized transactions directly.
- Remove private-key loading from the wallet diagnostics CLI.
- Preserve compatibility imports while failing closed with `SigningDisabled`.
- Add regression tests for the disabled signer and keyless diagnostics command.

## Security rationale
The legacy direct signer was a second signing surface outside `ControlledExecution`. It did not require the controlled quote validation, transaction-plan inspection, RPC simulation, or persistent idempotency workflow. Keeping that path available would undermine the intended execution boundary.

## Safety properties
- The compatibility signer does not decode, retain, log, or sign with supplied key material.
- Wallet diagnostics do not read environment settings or access a private key.
- This change does not enable transaction signing, transaction broadcast, wallet loading, or live trading.
- The application remains paper-only.

## Validation
- Regression tests added in `tests/unit/test_legacy_signer_lock.py`.
- Tests have NOT been executed in this change session.
- GitHub Actions status must be checked before merge. No CI success is claimed.

## Follow-up
- Review the complete ControlledExecution dependency graph and enforce Risk/Safety approval as a mandatory independent veto before any future signer implementation.
- Validate the exact Solana transaction message, fee payer, signer set, program allowlist, destination allowlist, spend caps, expiry, and simulation result at the signing boundary.
- Keep RPC broadcast disabled until recovery/reconciliation and operational kill-switch tests pass.
