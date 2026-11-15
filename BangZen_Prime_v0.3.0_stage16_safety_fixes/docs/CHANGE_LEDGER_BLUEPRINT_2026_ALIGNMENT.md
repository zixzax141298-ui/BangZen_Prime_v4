# Change ledger: Master Blueprint 2026 alignment (documentation only)

**Owner direction:** adopt `BANGZEN_PRIME_MASTER_BLUEPRINT_2026.md` as the mandatory structure for
now and align AI_RULES.yaml, RULES.md, AGENTS.md, and SECURITY.md with it.
**Scope:** documents only. No code, provider, risk threshold, or execution behaviour changed.

## Changed

| File | Change |
|---|---|
| `BANGZEN_PRIME_MASTER_BLUEPRINT_2026.md` | Added as a root governance document, text as supplied. |
| `AI_RULES.yaml` | Precedence now lists constitution and blueprint. The transition clause that allowed CI bypass (`ACTIVE_UNTIL_FURTHER_NOTICE`) is replaced by `NO_BYPASS`. Added `halt_flag` (REQUIRED_NOT_YET_IMPLEMENTED) and `master_blueprint_alignment`. YAML parsed successfully after the change. |
| `RULES.md` | New section 9: blueprint precedence, structure rule, watch-only, fail-closed, net PnL, HALT.flag status, CI no-bypass. |
| `AGENTS.md` | New section 1a: read blueprint and mapping before adding capability; no new folder or duplicate provider without approval; no test weakening. |
| `SECURITY.md` | New section 7a: HALT.flag status, live lock, provider data untrusted, fail-closed. |
| `docs/STRUCTURE_MAPPING_2026.md` | New. Maps every blueprint folder to the existing repository location, with status (Present, Partial, Duplicated, Legacy, GAP) and action (KEEP, FIX, REPLACE, ADD). Paths verified on disk. |
| `docs/governance/README.md` | Points to the blueprint and the mapping. |

## Conflicts found and how they were resolved

1. **CI bypass vs blueprint section 20.1.** AI_RULES allowed skipping legacy tests. The blueprint forbids weakening tests for green CI. Resolved to the blueprint (NO_BYPASS). **Owner confirmation needed** if an exception is still wanted for specific legacy tests.
2. **AI outcome analysis vs constitution.** Blueprint section 14 asks AI to summarise outcomes and explain strategy performance. Constitution v14.2 and AI_RULES forbid AI from analysing wins, losses, or profit. Resolved to the constitution. Performance analysis is deterministic (blueprint section 18). **Owner confirmation needed.**
3. **Folder layout.** Blueprint uses `core/`, `data/`, `strategies/` and similar. Repository uses `domain/`, `application/`, `infrastructure/`. Resolved as a logical map (`docs/STRUCTURE_MAPPING_2026.md`) with no physical migration yet. **Owner decision needed** on whether to migrate.
4. **Environment names.** Blueprint names lack the `BANGZEN_` prefix that the code enforces. Resolved by mapping. **Owner confirmation needed** only if the prefix should change (not recommended).
5. **Test runner.** Blueprint says Pytest. RULES says stdlib unittest is canonical. Resolved to unittest; Pytest optional for new tests.
6. **Quality tools.** Blueprint lists Black, Ruff, Mypy, Bandit, Semgrep, Safety, Pip-Audit. `tools/ci.py` runs none of them (checked). Resolved as NOT_RUN until added to the gate.
7. **Birdeye.** Blueprint lists a Birdeye provider. Only a setting exists, no adapter. Recorded as GAP. Adding it needs owner approval of the provider (blueprint 4.1 and AI_RULES `Adding a secret-bearing provider`).

## Not implemented (blueprint requirements still open)

- HALT.flag kill switch (blueprint 11.2, 21). Only `BANGZEN_EMERGENCY_STOP` exists.
- CTO strategy, RSI + Volume strategy as blueprint 9.1, walk-forward, out-of-sample, performance reports, reports directory.
- Consolidation of duplicate Jupiter, Jito, and Telegram adapters.
- PostgreSQL (blueprint section 17 target, SQLite in use).

## Verification

- `AI_RULES.yaml` parsed with PyYAML: valid.
- Grep: no remaining `ACTIVE_UNTIL_FURTHER_NOTICE` or bypass wording outside archived history.
- Code and tests were not changed by this record. Test status is unchanged from the previous ledger: 12 modules still need `httpx`, which is not installed in this sandbox.

## Rollback

Restore the previous `AI_RULES.yaml` integration clause from the prior package if the owner rejects
resolution 1. Remove the blueprint file and mapping doc to return to the previous document set.
