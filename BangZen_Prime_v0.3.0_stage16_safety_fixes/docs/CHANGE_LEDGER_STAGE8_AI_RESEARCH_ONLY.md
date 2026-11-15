# Change ledger: Stage 8, AI is research-only (option 3)

Owner answer in chat on 2026-11-15: AI is for data analysis only. Execution uses the existing API keys.
This replaces the deny-only design from stage 3 (option 1).

## Code
- `execution/controlled_execution.py`: removed the `pretrade_gate` parameter, its check, and the `AIDecision` import.
  Broadcast now depends only on the Risk Gate and the configured signer and broadcast flags.
- `research/ai_brain.py`: removed `ai_decision_gate` and `ai_gate` (no production caller).

## Tests (owner-approved removals and changes)
- `tests/integration/test_controlled_execution.py`: removed the AI parameters from `make()`, and the AI-only tests
  (absent gate, model SKIP veto at threshold, model BUY non-approval, fallback, low confidence).
  Renamed `test_risk_veto_blocks_even_when_ai_approves` -> `test_risk_veto_blocks_broadcast`.
  Renamed `..._before_ai_or_quote` -> `..._before_quote`. 34 tests pass.
- `tests/unit/test_ai_brain_hardening.py`: removed the three tests for the removed gate adapters.
- `tests/e2e/test_v3_flow.py`: removed the `ai_gate` argument, and `test_skip_recommendation_blocks_order`
  (it asserted the removed AI gate).

## Governance text (owner-approved in chat)
- `AI_RULES.yaml`: `halt_flag.status` -> `IMPLEMENTED`. `master_blueprint_alignment.structure.rule` -> section 15 layout.
- `SECURITY.md` 7 and 7a: HALT.flag implemented; no AI pre-trade gate in the execution path.
- `AGENTS.md` 1a: HALT.flag implemented.

## Test status
- Full suite: 904 tests. Failures: 5 FAIL, 2 ERROR. Baseline was 3 FAIL, 5 ERROR.
- The 2 extra FAILs are `WatchdogHaltTest.test_operator_reset_restores_trading` and
  `test_stale_worker_halts_new_paper_positions`. Before, they ERRORed because `paper_uc` passed `ai_gate`
  to `PaperTradingUseCase`, which does not accept it.
- Their new failure is `MARKET_PRICE_UNAVAILABLE`. The `paper_uc` helper does not pass `price_lookup`, so the
  paper engine rejects every fill. The other paper-flow tests fail for the same reason. NOT fixed here:
  fixing the fixture changes what these tests check, so it needs owner approval.
