# Change ledger: Stage 9, duplicate providers and notifiers consolidated (owner-approved in chat)

Owner choices on 2026-11-15:
- Telegram: keep `notifications/telegram.py` (the one bootstrap uses). Remove `notifications/messaging_telegram.py`.
- Jupiter: remove `data/providers/jupiter_v2.py` only. Keep `jupiter.py` (bootstrap) and `jupiter_quote_v2.py` + normalizer.

## Deleted
- `bangzen_prime/notifications/messaging_telegram.py`
- `bangzen_prime/data/providers/jupiter_v2.py`
- `tests/unit/test_telegram.py` (17 tests, only for messaging_telegram)
- `tests/unit/test_jupiter_v2_adapter.py` (5 tests, only for jupiter_v2)
- In `tests/unit/test_hardening_v4.py`: `TelegramLengthTest` (2 tests) and the messaging import.
- In `tests/unit/test_security_regressions.py`: `TelegramTruncationTests` (2 tests) and the messaging import.

## What is lost (read this before merging)
The deleted Telegram module was the only place with these features. After this change they exist nowhere in the repo:
- HTML escaping of signal text, and the `[SIGNAL ONLY | PAPER]` label.
- Message truncation at Telegram's UTF-16 limit, with no dangling HTML entity.
- 429 `retry_after` handling and the 60-second duplicate-message cooldown.
- Read-only `/status` and `/health` command replies to allowlisted chats.
The remaining `notifications/telegram.py` sends plain text only, with the 4096-character check.
It has no command handler. Restoring any of these needs a separate, owner-approved change.

## Test status
- Full suite: 878 tests. Failures: 5 FAIL, 2 ERROR. Same failure set as before this change
  (see CHANGE_LEDGER_STAGE8_AI_RESEARCH_ONLY.md).
