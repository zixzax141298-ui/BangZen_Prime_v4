# Change Ledger — P4 Verified Mint Metadata Gateway

## Change identity

- PR: #45
- Branch: `feat/p4-verified-mint-metadata-gateway`
- Base branch: `main`
- Base SHA: `3b5c75cc72b38c57a16983d0f8e9755b8f1dfca2`
- Objective: obtain verified mint decimals from finalized Solana account state.

## Files

- `bangzen_prime/domain/mint_metadata.py`
- `bangzen_prime/infrastructure/adapters/chain/helius_mint_metadata.py`
- `bangzen_prime/infrastructure/adapters/chain/helius.py`
- `tests/unit/test_helius_mint_metadata.py`
- `docs/MINT_METADATA_GATEWAY.md`
- `docs/CHANGE_LEDGER_P4_VERIFIED_MINT_METADATA.md`

## Invariants

- No risk thresholds, strategy scoring, AI authority, or execution permissions changed.
- No secret is embedded in code or returned in exception text.
- The reader only calls injected read-only account-info RPC.
- Unsupported owner, missing account, malformed payload, and uninitialized mint do not
  yield usable decimals.
- Token-2022 extensions are not parsed; this is explicitly disclosed.
- No test or CI result is claimed unless the exact command is run.

## Validation status

- Unit tests authored; **NOT RUN** in the authoring environment.
- `python3 tools/ci.py`: **BLOCKED / NOT RUN**; the required script was not present on
  the inspected `main` tree at PR creation.
- GitHub Actions run #545 on the earlier head: Python 3.12 FAILURE; Python 3.11 CANCELLED. Both attempts exposed empty step summaries and job-log retrieval returned 404.
- GitHub Actions run #547 on current head SHA `66c637e`: Python 3.11 FAILURE; Python 3.12 CANCELLED. Step summaries were empty and job-log retrieval returned 404, so the cause is unknown.
- Failed jobs for run #547 were re-run. Attempt 2 also completed with Python 3.11 FAILURE and Python 3.12 CANCELLED. Both attempts had empty step summaries and no retrievable logs.
- Current-head CI is therefore not verified green. No test pass or production readiness is claimed.

## Rollback

Revert PR #45. No database migration, persistent state, or external side effect is added.
