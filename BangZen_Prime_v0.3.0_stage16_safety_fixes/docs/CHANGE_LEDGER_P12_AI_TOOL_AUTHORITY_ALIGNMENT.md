# Change Ledger P12 — AI tool authority alignment and policy test enforcement

## Objective and non-goals
- Objective: remove the contradiction between AI-exposed tools and the weapon catalog's `DENIED` access; add an explicit tool-to-weapon bridge; make policy guard tests actually execute under the canonical runner; stop silent loss of AI tool configuration.
- Non-goals: no change to risk thresholds, sizing, SL/TP, fees, slippage, safety filters, or live-execution lock. No new evidence producers. Lifecycle phase vocabulary is not reconciled in this change.

## Owner authorization
Repository owner granted mandate for AI decision-authority alignment (AI_RULES `owner_approval_required_for`). The change only reduces AI authority.

## Files changed
- config/ai_tools.json: removed `run_black_ops` and `evaluate_second_life` (catalog `DENIED`).
- config/strategy_matrix.json: removed those two from scenario `candidate_weapons`; every scenario keeps at least one candidate.
- config/ai_tool_weapon_map.json: new explicit bridge, AI tool name -> catalog weapon id.
- bangzen_prime/application/ai_commander.py: `_load_tools` resolves config relative to repository root, logs a warning on unavailable/invalid config instead of silently returning an empty list.
- tests/unit/test_ai_weapon_config_policy.py: allowlist updated to the reduced surface; two new tests (bridge consistency, no scenario routes to a denied capability); converted from pytest-style functions to `unittest.TestCase`.
- tests/unit/test_weapon_catalog_policy.py: converted from pytest-style functions to `unittest.TestCase`; assertions unchanged.
- docs/CHANGE_LEDGER_P12_AI_TOOL_AUTHORITY_ALIGNMENT.md: this file.

## Compatibility, migration, rollback
No database migration. AI tool list is not sent to any provider in current code, so runtime behaviour is unchanged. Rollback: restore the three config files and the two test files and revert ai_commander.py.

## Security and risk impact
Reduces AI surface by two tools. Removes routing to a placeholder (`second_life_strategy`). Live execution remains locked.

## Validation actually run
- `python3 scripts/run_tests.py` (offline, no httpx available): 699 discovered, 687 passed, 12 errors. All 12 are `ModuleNotFoundError: httpx` (environment), identical to baseline before the change.
- `python3 -m unittest tests.unit.test_ai_weapon_config_policy tests.unit.test_weapon_catalog_policy`: 8 tests, all OK (previously 0 executed by the canonical runner).
- The new/updated AI-policy tests FAIL against the original config (verified), so they detect the defect.
- `py_compile` on changed Python files: OK.

## Checks NOT run and why
- `python3 tools/ci.py` (full gate): NOT RUN. Dependencies unavailable offline (httpx, black, ruff, mypy, bandit, semgrep, pip-audit, pytest).
- 12 httpx-dependent test modules including `test_ai_commander_sybil_gate`: NOT RUN.
- `_load_tools` change: not directly tested (module imports httpx-dependent adapters).

## Known limitations
- Lifecycle weapon policy evidence types (e.g. `funding_graph`, `pool_state`) have no producers in code.
- Lifecycle phase vocabularies differ across `application/lifecycle.py`, `phase_policy`, `lifecycle_weapon_router`, and `domain/lifecycle.py`.
- `check_smart_money_quality` maps to a thin wrapper (`IMPLEMENTED_STUB`).

## Status
Implementation: staged. Test (offline subset): PASS for affected config tests. CI gate: NOT RUN / NOT GREEN. Review: pending owner. Merge: not performed. Live execution: remains locked.
