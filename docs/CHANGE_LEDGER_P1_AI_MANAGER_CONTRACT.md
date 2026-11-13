# Change Ledger — P1 AI Manager Evidence Contract

## Objective

Introduce a strict, versioned evidence and decision boundary plus deterministic selection of at most one allowlisted weapon, before integrating AI Manager behavior with existing production orchestration.

## Base and branch

- Repository: `ripsterxiui98-coder/BangZenPrime-v3`
- Base branch: `main`
- Base SHA: `3c6136d6d79f5ffd67e855e9946ebde8bd79b2c1`
- Branch: `feat/p1-ai-manager-evidence-contract`
- Head SHA: see the PR head commit metadata (the ledger intentionally avoids a self-referential commit hash).

## Files

- `bangzen_prime/application/ai_manager_contract.py`
- `tests/unit/test_ai_manager_contract.py`
- `docs/AI_MANAGER_CONTRACT.md`
- `docs/CHANGE_LEDGER_P1_AI_MANAGER_CONTRACT.md`

## Non-goals

- No provider or LLM calls.
- No changes to existing AIBrain, AICommander, strategy thresholds, risk limits, or BUY/SKIP/WATCH behavior.
- No live trading, signer, transaction construction, or broadcast.
- No historical completeness claim or automatic replay/reconciliation.
- No automatic strategy execution; weapon selection returns metadata only.

## Validation

- Existing AI brain, AI commander, security, architecture, and policy files inspected.
- Unit tests added for strict schema validation, status/freshness, subject consistency, deterministic one-weapon selection, and safe decision invariants.
- Tests and static checks: NOT RUN in this authoring environment.
- `python3 tools/ci.py`: NOT RUN; file is absent from the current main tree.
- No CI, test, or production-readiness pass is claimed.

## Known limitations

- This is an additive contract only; it is not yet wired to the legacy AICommander.
- The selector is deterministic allowlist infrastructure, not autonomous strategy learning.
- Evidence freshness is enforced against an explicit caller-supplied maximum age. Provider-specific freshness policy must be defined in a later evidence aggregation PR.
- The contract requires a complete VERIFIED record for eligibility, but does not prove that provider coverage is globally complete.
- Owner review is required before merging.
