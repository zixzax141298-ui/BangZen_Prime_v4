# Change ledger: Stage 5, structure migration to blueprint section 15

Applied on top of stages 1 to 4 (not on the original tree), so the stage fixes stay in the moved files.
Mapping: `docs/STRUCTURE_MIGRATION_2026.md` (module table) and `scratchpad/migrate/mapping.py`.

## Done
- `domain/`, `application/`, `infrastructure/`, `filters/`, `native/` layers removed. Modules moved to
  `core/`, `data/`, `discovery/`, `security/`, `market/`, `strategies/`, `scoring/`, `risk/`,
  `execution/`, `notifications/`, `analytics/`, `research/`, `storage/`.
- `application/halt.py` -> `risk/emergency_stop.py` (blueprint slot for HALT.flag, section 11.2/21).
- `config/` -> `configs/`. References updated in `research/ai_commander.py` and 5 tests.
- Blueprint folders created (empty, with `.gitkeep`): `tests/security`, `tests/regression`,
  `tests/fixtures`, `reports/daily`, `reports/evaluation`.
- Imports rewritten by script. Manual fixes after the script: `from bangzen_prime.native import rust_bridge`
  -> `core`, one `from bangzen_prime.application import ...` in a test -> `core` and `execution`,
  negative tests retargeted to `bangzen_prime.execution.burner_wallet` and `.ed25519`,
  grpc stub path updated to `bangzen_prime.data.providers.yellowstone_pb2`.

## Verification
- `compileall` on `bangzen_prime` and `tests`: OK.
- Full suite: 913 tests, failure set identical to the pre-migration tree
  (3 failures, 5 errors, all pre-existing in the original code).
- The migration tool's AST import checker reports the pre-existing stale string references and the
  `market/market_analyzer.py` missing-module references (already in the original code).

## Still open (owner approval)
- Governance files still describe the old layout: `AI_RULES.yaml` (`repository_layout`,
  `master_blueprint_alignment`), `AGENTS.md`, `SECURITY.md`, `RULES.md`, `docs/STRUCTURE_MAPPING_2026.md`.
- Duplicates kept: Jupiter (`jupiter.py`, `jupiter_v2.py`, `jupiter_quote_v2.py`), Telegram
  (`notifications/telegram.py`, `notifications/messaging_telegram.py`). Consolidation is a later PR.
- `grpc_stream` needs `yellowstone_pb2`, which is not in the repo.
- Root-level `test_sniper.py`, `watchlist.txt`, `data/`, `native/` are outside the blueprint list. Not moved.
