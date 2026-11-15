# Owner decision required: AI approval boundary (audit F5, Stage 3)

Status: DECIDED (option 1, deny-only AI). AI_RULES `conflict_policy` asks for owner clarification. The owner
delegated the choice to the assistant in chat on 2026-11-15 ("lanjutkan dengan keputusan yg lebih baik dan aman").
Owner answer in chat on 2026-11-15 selected option 3 (AI for data analysis only; execution uses the existing
API keys). Option 1 was applied first, then replaced by option 3 in stage 8.

## The conflict
- AI_RULES `ai_research_boundary.forbidden`: AI must not make BUY, SELL, HOLD, or EXECUTE decisions.
- SECURITY.md section 6: AI output is never execution authorization.
- SECURITY.md section 7: FAST PATH must not depend on AI.
- Current code: `controlled_execution.py` approves a trade only when the AI returns `BUY` with
  source `model`, and rejects with `AI_APPROVAL_UNAVAILABLE` when no AI gate is set.
- Current tests lock that behaviour in: `test_broadcast_requires_ai_approval_gate`,
  `test_fallback_ai_decision_cannot_approve_broadcast`, `test_low_confidence_ai_buy_cannot_approve_broadcast`.

Note: `ControlledExecution` is not wired into `bootstrap.py` or the CLI today, so the impact is latent.

## Options
1. **Deny-only AI (recommended).** AI can only veto with a model `SKIP` above the confidence threshold.
   AI unavailability or fallback does not block execution. The deterministic Risk Engine still decides.
   Change: rewrite the gate, and change the tests above to assert the new behaviour.
   This matches SECURITY section 7. It also means these tests assert a different rule, which is an
   owner-approved change, not a silent weakening.
2. **Keep AI as a required approval.** Accept the conflict in writing and update SECURITY section 6 and 7
   to say so. Blocks FAST PATH on AI outages.
3. **Remove AI from execution entirely.** AI stays research-only. Delete the pre-trade gate.

Also to decide: the model vocabulary still says `BUY` / `SKIP`. AI_RULES forbids `BUY` from AI output
at all. Renaming the output to research-only is a separate contract change with its own tests.

Recommendation: option 1 now, and the vocabulary change as a follow-up PR.

Decision applied: option 1 (deny-only AI), in `docs/CHANGE_LEDGER_STAGE3_AI_DENY_ONLY.md`.
Owner signature: PENDING (delegated in chat 2026-11-15, not yet signed in the governance file).
AI_RULES and SECURITY.md text still describe the old boundary; updating them needs owner approval.
