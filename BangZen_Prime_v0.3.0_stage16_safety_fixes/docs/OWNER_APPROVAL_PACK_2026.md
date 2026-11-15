# Owner approval pack (stage 7)

These changes need the owner's written approval. The assistant has NOT applied any of them.
Code changes that are already in the tree are listed as "done" so the owner can review them together.

## A. Governance text to update (needs approval)
1. `AI_RULES.yaml`
   - `halt_flag` status: `REQUIRED_NOT_YET_IMPLEMENTED` -> `IMPLEMENTED` (`risk/emergency_stop.py`, stage 1).
   - `ai_research_boundary`: state that AI may only veto with SKIP at or above threshold, and never approves
     (stage 3, option 1). Remove the `BUY`-as-approval wording.
   - `repository_layout` and `master_blueprint_alignment`: point to the blueprint section 15 layout (stage 5).
2. `SECURITY.md`
   - Section 6 and 7: deny-only AI wording (stage 3).
   - Section 7a: HALT.flag is implemented; update the status.
3. `AGENTS.md`, `RULES.md`: replace the old layer names (`domain/`, `application/`, `infrastructure/`) with the new folders.
4. `docs/STRUCTURE_MAPPING_2026.md`: update the mapping table to the new paths.

## B. Tests whose asserted rule changed (needs approval)
- `tests/integration/test_controlled_execution.py`:
  - `test_broadcast_requires_ai_approval_gate` -> `test_absent_ai_gate_does_not_block_broadcast`
  - `test_fallback_ai_decision_cannot_approve_broadcast` -> `test_fallback_ai_skip_cannot_veto`
  - `test_low_confidence_ai_buy_cannot_approve_broadcast` -> `test_low_confidence_model_skip_cannot_veto`
  - new: `test_model_skip_at_threshold_vetoes_before_quote_and_signing`, `test_model_buy_never_approves_but_does_not_veto`

## C. Owner decisions still open (no default applied)
1. AI output vocabulary: `DECISIONS = ("BUY", "SKIP")` in `ai_brain.py`. AI_RULES forbids BUY from AI output.
   Rename is a separate PR with its own tests.
2. Supervisor emergency-stop semantics: it is unused in production, and its test encodes "skip only order-placing workers".
3. Black in the termux profile versus the test that expects Black to be excluded there.
4. `DevPredictorAdapter` (`security/dev_predictor_adapter.py`): `check_dev_new_mint` always returns
   `clean_no_recent_mint`. It is a stub that fails open. Do NOT wire it into bootstrap until it has a real
   implementation and a fail-closed default. Its unused construction in `core/bootstrap.py` was left in place on purpose.
5. `KOLExitAdapter` is built with an empty `smart_money_wallets` set. Same rule: not wired, no change made.
6. `ai_brain.ai_gate` still returns allowed only on `BUY`. No production caller; only e2e tests use it.

## D. Done in code (for review)
- Stage 1: HALT.flag and emergency stop on monitor, outbox, CLI, and WebSocket.
- Stage 2: CI gate integrity (skips removed, ordered name check, `--allow-skips` default 0, new checks registered).
- Stage 3: AI deny-only in `ControlledExecution`.
- Stage 4 (partial): Rust bridge ignores a `bangzen_native` found in the working directory.
- Stage 5: structure migration to blueprint section 15.
- Stage 6: safe Ruff fixes (import order, unused imports).
- Stage 7: removed two dead variables (`last_exc` in async_retry, unused assignment in strategy dispatcher).

## E. Not done (environment or scope)
- F6: dependency hashes and pinned rustup/maturin (no network to PyPI in this session).
- Bandit, Semgrep, Pip-Audit, Cargo Audit: tools not installed.
- Black across the tree and mypy: separate PR.
- Duplicate Jupiter and Telegram modules: consolidation deletes tests, so it needs owner approval first.
