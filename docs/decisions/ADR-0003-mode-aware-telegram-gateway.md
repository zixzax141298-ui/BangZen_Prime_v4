# ADR-0003: Mode-Aware Outbound Telegram Signal Gateway

- Status: Proposed in PR #55
- Date: 2026-11-13
- Related policy: AI_RULES.yaml v13.0, SECURITY.md, RULES.md
- Depends on: PR #54 removal of the plaintext burner wallet

## Context

BANGZEN PRIME has a three-mode domain contract, Telegram configuration fields, and a signal outbox, but the operating mode was not applied at the notification boundary and no dedicated outbound Telegram adapter was wired into the composition root.

## Decision

Add a strict `BANGZEN_OPERATING_MODE` setting with values `TELEGRAM_ONLY`, `EXECUTION_ONLY`, and `HYBRID`, defaulting to `TELEGRAM_ONLY`. Wire the controller into bootstrap and gate notifier delivery using the controller's effective Telegram permission.

Add an outbound-only Telegram notifier that sends plain text to configured numeric allowlisted chat IDs. Require bot token and allowlist configuration as a pair. Do not implement inbound polling, bot commands, wallet access, signing, or transaction submission.

## Safety semantics

The mode is not a permission to execute. In all three modes, `wallet_access_allowed` and `execution_available` remain false because live execution is disabled by the governing policy and the kill switch remains engaged.

## Consequences and limitations

- `EXECUTION_ONLY` suppresses Telegram notifications but does not enable live trading.
- `HYBRID` sends Telegram notifications but does not enable live trading.
- Without Telegram credentials, the app retains its offline log notifier.
- Current signal event data lacks mint, symbol, source provenance, and observation timestamps; the existing internal token UUID must not be misrepresented as a mint address. This requires a separate domain-event contract change.
- Outbox delivery is at-least-once; duplicate messages can occur after uncertain delivery outcomes.

## Validation

Tests are added for mode gating, allowlist validation, outbound request shape, token redaction, and configuration parsing. They must be run in CI; code inspection is not a passing test result.
