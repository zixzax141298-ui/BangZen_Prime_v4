# ADR-0005: Watch-Only Public Wallet Registry

- Status: Proposed in PR #58
- Date: 2026-11-13
- Depends on: PR #54 removal of the plaintext burner wallet

## Context

The project needs a safe way to identify a user-created Solana wallet without giving the bot possession of its recovery phrase or signing key. A local lock cannot freeze an on-chain address, and a public address can receive assets even when the bot is in Telegram-only mode.

## Decision

Accept only an optional public address through `BANGZEN_WALLET_PUBLIC_ADDRESS`. Validate its base58-form address syntax and store it in a watch-only registry. Hide the address from settings and diagnostic representations to reduce accidental exposure of the user's wallet activity.

The `WalletAccessController` reports the current operating mode, public-address registration state, emergency-stop state, and explicit denial reasons. It always reports signer access and fund usage as unavailable. Both signing and fund-use assertions fail closed. The API accepts no seed phrase, private key, signer object, or transaction data.

## Consequences

- The user may create a wallet outside BANGZEN and configure only its public address.
- BANGZEN can identify the watch-only address but cannot create/import the wallet, sign, or trade.
- No on-chain deposit can be prevented by an application setting. The bot can only refuse to use funds.
- This does not implement a secure signer. Any future signer requires explicit owner approval, a separate architecture decision, independent security review, and full execution-path tests.
