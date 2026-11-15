# Operating Modes and Execution Lock

## Scope

This change introduces an explicit mode contract and a fail-closed application
controller. It does not enable live trading, create a wallet, load a private
key, sign transactions, or broadcast transactions.

## Modes

| Mode | Telegram signals | Execution requested | Effective wallet access in this release |
|---|---:|---:|---:|
| `TELEGRAM_ONLY` | On | No | Denied |
| `EXECUTION_ONLY` | Off | Yes | Denied |
| `HYBRID` | On | Yes | Denied |

A requested mode is not an execution authorization. The effective permission
is the intersection of the requested mode, the kill switch, and the separately
approved live-execution policy. Live execution remains disabled by the
repository constitution.

## Kill switch

- Starts engaged on every controller instance.
- Switching to `TELEGRAM_ONLY` engages it.
- It can be engaged explicitly at any time.
- This PR deliberately has no disarm/reset operation.
- The controller has no wallet, signer, RPC, or transaction dependencies.

A future proposal for execution must first receive explicit owner approval to
revise the governing policy, then undergo a separate signer/execution security
review. A mode toggle alone must never unlock funds.

## Funding and wallet semantics

A Solana public address can receive SOL or tokens on-chain regardless of this
application's selected mode. The bot cannot prevent an external transfer to
that address. In `TELEGRAM_ONLY`, the application must not obtain signer
access or use wallet funds. This PR keeps wallet access denied in every mode.

A local kill switch is an application control, not an on-chain freeze or key
revocation. If a key is compromised, assets must be moved to a new secure
wallet; a local flag cannot invalidate a Solana private key.

## Validation and rollback

- Unit tests cover mode combinations, default lock, kill-switch latching,
  invalid mode input, and denied execution.
- No network, wallet, or signing operations are part of these tests.
- Rollback: revert this PR; no migration or persistent state is introduced.

## Runtime configuration and Telegram boundary

The selected user-facing mode is configured at startup with `BANGZEN_OPERATING_MODE` (default `TELEGRAM_ONLY`). The value is validated against the three enum values; unknown values fail configuration. The application composition root constructs the mode controller and applies a Telegram delivery gate before the notifier.

The Telegram adapter is outbound-only. It sends formatted signal text to configured numeric chat IDs, does not poll updates, does not expose bot commands, and has no wallet or transaction dependency. The token is used only by this adapter and is excluded from object representations and exception messages. Configure the bot token and allowlist together; a partial configuration is rejected.

Even in `EXECUTION_ONLY` and `HYBRID`, the controller's effective execution permission and wallet access remain denied because live execution is disabled by policy. This PR does not add signing, balance access, or transaction submission. Outbox delivery remains at-least-once, so duplicate Telegram messages are possible after an uncertain delivery outcome.

## Watch-only public wallet registry

The optional `BANGZEN_WALLET_PUBLIC_ADDRESS` setting accepts only a validated Solana public address. It is public identity metadata, not a seed phrase, private key, signer, or proof of ownership. The application stores only this address in its in-memory watch-only registry. The wallet access controller reports signer access and use of funds as unavailable in every operating mode; the emergency stop adds an explicit veto reason.

Do not place seed phrases or private keys in `.env`, source code, Telegram, GitHub, or ChatGPT. Create any wallet outside BANGZEN using a trusted wallet or hardware signer and keep recovery material offline. This release cannot create/import a wallet or sign transactions. An external transfer can still arrive at any public address regardless of app mode; the bot cannot freeze or prevent on-chain deposits. Do not fund a wallet for bot execution until a separately approved signer and end-to-end security review exist.

## Wallet registry implementation boundary

The optional `BANGZEN_WALLET_PUBLIC_ADDRESS` is validated as a base58-form Solana address and registered as watch-only metadata. `WalletAccessController` reports the active mode, configured public identity, emergency-stop state, and reason codes. It always reports `signer_available=false` and `funds_usable=false`; both signer and fund-use assertions raise a permission error. No wallet secret or signer handle is accepted by this API.
