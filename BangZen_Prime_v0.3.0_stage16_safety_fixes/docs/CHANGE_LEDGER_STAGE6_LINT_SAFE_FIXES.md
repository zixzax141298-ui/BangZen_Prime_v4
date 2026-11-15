# Change ledger: Stage 6, safe lint fixes

Scope: only `ruff --fix` for rules I001 (import order), F401 (unused import), and F841 (unused local).
No logic change, no test change, no test removed. Black was not applied to the whole tree,
because the original tree already fails `black --check` in many files.

## Result
- Ruff findings on the migrated tree: 323 -> 9 (the 9 left are not in the safe set).
- Removed unused imports in: `core/bootstrap.py`, `core/interfaces/dashboard.py`, `tests/unit/test_hardening_v4.py`
  and similar. Re-exports in `strategies/__init__.py` were kept (ruff does not touch them without an unsafe fix).
- Remaining unused locals left on purpose (need a human read): `bootstrap.py` `dev_predictor`/`kol_exit`
  (they may be wiring kept for side effects), `async_retry.py` `last_exc`, `strategy_dispatcher.py` `loop`.

## Verification
- Full suite (913 tests): same failure set as the stage 5 tree (3 failures, 5 errors, pre-existing).
- `compileall` on `bangzen_prime` and `tests`: OK.

## Still open
- Black across the tree (about 5 original files and more), mypy (about 101 in the original code),
  and the remaining 9 Ruff findings.
