# Change ledger: Stage 3, AI pre-trade gate is deny-only (audit F5)

Decision: option 1 of `DECISION_REQUIRED_AI_APPROVAL_BOUNDARY.md`, chosen under the owner's
delegation in chat on 2026-11-15. Owner signature pending.

## Behaviour change (`bangzen_prime/execution/controlled_execution.py`)
- Before: a BROADCAST needed a model `BUY` with confidence >= threshold. No gate, or a gate error,
  rejected with `AI_APPROVAL_UNAVAILABLE` or `AI_APPROVAL_DENIED`.
- After: AI can only veto. A model `SKIP` with confidence >= threshold rejects with `AI_VETO`.
  No gate, a fallback decision, an exception, or a low-confidence answer never blocks.
  The deterministic Risk Gate still decides every trade. AI never approves a trade.
- Ordering unchanged: Risk Gate runs before the AI check, and both run before quote and signing.

## Tests (`tests/integration/test_controlled_execution.py`)
Replaced three tests that asserted the old approval rule. Owner approval is required for these changes:
- `test_broadcast_requires_ai_approval_gate` -> `test_absent_ai_gate_does_not_block_broadcast`
- `test_fallback_ai_decision_cannot_approve_broadcast` -> `test_fallback_ai_skip_cannot_veto`
- `test_low_confidence_ai_buy_cannot_approve_broadcast` -> `test_low_confidence_model_skip_cannot_veto`
Added: `test_model_skip_at_threshold_vetoes_before_quote_and_signing`,
`test_model_buy_never_approves_but_does_not_veto`.
`test_ai_veto_blocks_before_quote_and_signing` kept, and its reason is now `AI_VETO`.

## Not changed (flagged)
- `ai_brain.ai_gate` still returns allowed only on `BUY`. It has no production caller, only e2e tests.
- `DECISIONS = ("BUY", "SKIP")` vocabulary. AI_RULES forbids BUY from AI output. Rename is a separate PR.
- AI_RULES.yaml, SECURITY.md section 6/7, AGENTS.md still describe the old boundary. Owner approval needed.

## Verification
- `tests/integration/test_controlled_execution.py`: 39 passed.
- Full suite (913 tests): same failure set as before this change (3 failures, 5 errors, all pre-existing).
