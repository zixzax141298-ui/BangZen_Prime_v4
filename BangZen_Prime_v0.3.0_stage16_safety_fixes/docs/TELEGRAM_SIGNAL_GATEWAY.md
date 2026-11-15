# Telegram Signal Gateway

## Scope

This is an outbound-only signal notification adapter. It does not poll Telegram updates, register bot commands, accept BUY/SELL instructions, inspect wallet balances, access a signer, or submit transactions.

## Mode behavior

| `BANGZEN_OPERATING_MODE` | Telegram signal delivery | Effective wallet access |
|---|---|---|
| `TELEGRAM_ONLY` | Enabled | Denied |
| `EXECUTION_ONLY` | Suppressed | Denied |
| `HYBRID` | Enabled | Denied |

The operating mode is a presentation/notification preference, not a live-execution grant. Live execution and signing remain disabled by repository policy in every mode. The kill switch remains engaged.

## Recipient and credential controls

- Configure `BANGZEN_TELEGRAM_BOT_TOKEN` and `BANGZEN_TELEGRAM_ALLOWED_CHAT_IDS` together.
- Chat IDs must be numeric and explicitly allowlisted; duplicate or malformed IDs are rejected.
- The notifier sends only to those configured IDs. It does not discover or trust recipients from inbound Telegram messages.
- The bot token is held only by the Telegram adapter, excluded from `repr`, and never inserted into exception messages.
- The adapter uses the shared HTTPS request transport, bounded timeout, no redirects, and generic service errors.
- Plain text is used without Telegram parse modes to avoid markup interpretation of untrusted fields.

## Current signal payload limitations

Accepted signals now carry the validated Solana chain, mint, symbol, selected pair address, DEX ID, market provider source, and market observation timestamp, alongside the signal ID and heuristic price/score fields. The domain verifies that mint and pair addresses reproduce the stored token/pair identities before emitting those fields. If an older or incomplete event lacks this metadata, the formatter explicitly labels the mint as unavailable and falls back to the internal token UUID; it never fabricates an address.

## Delivery semantics

The outbox is at-least-once, not exactly-once. If a network outcome is uncertain or one recipient succeeds before another fails, a retry may produce a duplicate message. No transaction or trade is triggered by a notification retry.
