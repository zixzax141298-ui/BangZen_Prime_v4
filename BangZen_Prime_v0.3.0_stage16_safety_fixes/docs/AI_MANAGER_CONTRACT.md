# AI Manager — Evidence and Decision Contract v1.0

## Scope

This document defines the first application-level contract for the AI Manager. It is a pure, provider-agnostic boundary. It does not connect an LLM, fetch chain history, run a weapon, place a paper order, sign, or broadcast a transaction.

Implementation: `bangzen_prime/application/ai_manager_contract.py`.

## Evidence package

An evidence package has an exact schema version, one subject, a collection timestamp, and a bounded list of evidence records. Each record preserves:
- Evidence identifier and subject.
- Evidence type.
- Observation and receipt timestamps, including timezone.
- Provider/source and provider record identifier.
- Freshness age and completeness fraction.
- Validation status.
- Confidence basis and reason codes.

Unknown fields, missing fields, duplicate evidence IDs, mismatched subjects, invalid timestamps, non-finite numbers, and out-of-range completeness are rejected. Provider payloads must be normalized before they enter this contract.

### Eligibility

Only records with status `VERIFIED`, completeness exactly 1, valid timestamps, and age within the caller's explicit freshness budget are eligible for weapon requirements.

`PARTIAL`, `UNAVAILABLE`, `CONFLICTED`, and `REJECTED` are never treated as verified. Future-dated observations are ineligible. The freshness budget is a caller-supplied policy value; this contract does not invent a universal TTL.

A validated record proves only the stated source observation and scope. It does not prove token safety or complete blockchain history.

## One-weapon selection

`WeaponRegistry` is an allowlist of explicitly registered `WeaponSpec` values. Every weapon declares required evidence types, priority, and enabled state.

Selection:
1. Filter to verified, complete, fresh evidence.
2. Keep only enabled weapons whose full evidence requirements are satisfied.
3. Select exactly one by descending declared priority, then stable weapon ID for deterministic tie-breaking.
4. Return no weapon if no candidate is eligible.

This selector is deterministic scaffolding, not the AI's learned or autonomous strategy. It does not change thresholds, infer risk, or execute a module. A later PR may add evidence-driven risk classification and module adapters behind this contract.

## Decision actions

- `BUY_CANDIDATE`: advisory research recommendation only. Requires exactly one selected weapon, evidence references, reason codes, and `VERIFIED` data quality.
- `HOLD`: insufficient, stale, partial, or unavailable evidence; no weapon selected.
- `SKIP`: reject the candidate; no weapon selected.

No action in this contract authorizes an order. Deterministic Risk/Safety remains the final veto. Live trading, signing, and broadcast remain locked.

## Compatibility and migration

The contract is additive and is not wired into the legacy `AIBrain` or `AICommander` flow in this PR. Existing `BUY/SKIP/WATCH` consumers remain unchanged. Integration and deprecation of legacy decisions require a separate PR with call-site inventory and compatibility tests.
