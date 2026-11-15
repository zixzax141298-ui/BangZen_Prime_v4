# Change Ledger — P2 Lifecycle Weapon Router

## Objective
Add a strict, fail-closed selector that maps Pump.fun launch through bonding curve,
migration, Raydium pool, growth, distribution and revival phases to at most one
analysis-only weapon supported by fresh, complete, VERIFIED evidence.

## Base and head
- Repository: `ripsterxiui98-coder/BangZenPrime-v3`
- Base branch: `main`
- Base SHA: `84f20056dce49c19f563e2cd7352b7419f16cee6`
- Head SHA: recorded after branch commit creation.

## Files added
- `bangzen_prime/application/lifecycle_weapon_router.py`
- `config/lifecycle_weapon_policy.json`
- `tests/unit/test_lifecycle_weapon_router.py`
- `docs/LIFECYCLE_WEAPON_SYSTEM.md`
- `docs/CHANGE_LEDGER_P2_LIFECYCLE_WEAPONS.md`

## Compatibility and migration
- Additive Python module and JSON policy; no existing module or configuration is replaced.
- No database migration or dependency change.
- Existing `phase_policy.py` is preserved; this PR adds a separate analysis-weapon router,
  not a modification to paper-entry policy.

## Security and risk
- Explicit analysis-only allowlist; execution IDs are rejected at policy load.
- Requires the existing versioned `EvidencePackage` and only selects from eligible evidence.
- Selects zero or one weapon; no provider calls or model calls occur here.
- No financial authority, order planning, signing, broadcast, or live-mode change.
- Deterministic Risk/Safety remains the final veto.
- Does not claim every referenced adapter is complete or runtime-connected.

## Validation
- Unit tests added: `tests/unit/test_lifecycle_weapon_router.py`.
- Test execution: NOT RUN in authoring environment.
- `python3 tools/ci.py`: BLOCKED / NOT RUN; `tools/ci.py` is absent from the inspected main tree.
- Full CI, type checks, lint, security scans, and integration tests: NOT RUN.
- No test-pass, CI-green, profitability, or production-readiness claim.

## Known limitations
- Phase classification and evidence production are upstream responsibilities and are not wired
  to the live event stream in this PR.
- Weapon IDs are routing targets; some underlying modules are stubs, partial, or require
  adapter contract verification. Runtime invocation is intentionally not enabled here.
- Historical replay, phase-aware performance measurement, and real-time lifecycle integration
  remain follow-up work.

## Rollback
Delete the five additive files in a revert commit. No persisted data or external state changes.
