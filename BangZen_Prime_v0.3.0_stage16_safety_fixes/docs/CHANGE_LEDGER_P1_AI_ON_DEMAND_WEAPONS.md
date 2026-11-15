# Change Ledger — AI On-Demand Analysis Weapons

## Scope

- Restrict AI-visible tools to analysis-only weapons.
- Replace mandatory weapon checklists with scenario candidates and an at-most-one on-demand policy.
- Explicitly deny financial, order, and transaction authority to AI Manager.

## Files

- config/ai_tools.json: 11 analysis tools retained; four financial/execution-adjacent tools excluded from AI visibility.
- config/strategy_matrix.json: versioned policy, evidence-triggered scenarios, no mandatory all-weapons invocation, empty selection allowed.
- docs/AI_WEAPON_BOUNDARY.md: authority and integration boundary.
- tests/unit/test_ai_weapon_config_policy.py: config invariants.

## Safety

- No wallet keys, signing, transaction construction, submission, or broadcast added.
- No balances, position sizing, buy/sell plan, TP/SL, slippage, or TWAP exposed to AI Manager.
- Existing non-AI runtime implementations are not deleted.
- Runtime enforcement remains unverified until all provider/tool call sites are wired to this policy.

## Validation

- Tests added; NOT RUN in this authoring environment.
- No CI, static-analysis, or production-readiness pass is claimed.
