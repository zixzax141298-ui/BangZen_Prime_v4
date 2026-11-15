# Change Ledger — P4 Token Program Evidence Gateway

## Identity

- PR: #50
- Branch: feat/p4-token-2022-discovery-paper-risk-gateway
- Base: main
- Base SHA: 7a12544eb18891419615d3914f28dc22a63f8962
- Objective: wire exact mint-owner and Token-2022 extension evidence into Solana discovery and paper-entry RiskEngine.
- Final head SHA: see PR metadata after all commits.

## Files changed

- bangzen_prime/domain/token_programs.py
- bangzen_prime/domain/signals.py
- bangzen_prime/application/token_program_evidence.py
- bangzen_prime/application/use_cases.py
- bangzen_prime/application/risk_engine.py
- bangzen_prime/application/paper_trading.py
- bangzen_prime/bootstrap.py
- tests/unit/test_token_program_evidence.py
- tests/unit/test_risk_engine.py
- tests/unit/test_token_2022_extensions.py
- tests/unit/test_token_2022_risk_engine_integration.py
- tests/e2e/test_scan_flow.py
- tests/e2e/test_paper_flow.py
- tests/e2e/test_v3_flow.py
- docs/TOKEN_PROGRAM_EVIDENCE_GATEWAY.md
- docs/CHANGE_LEDGER_P4_TOKEN_PROGRAM_EVIDENCE_GATEWAY.md

## Invariants

- Only exact canonical classic SPL Token owner evidence with a validated initialized mint layout is NOT_APPLICABLE.
- Token-2022 must pass fresh, exact-mint, VERIFIED extension/configuration evidence.
- Missing/unknown/stale/partial/provider-error states never silently become classic SPL Token.
- Classic SPL Token is N/A only after owner, initialized 82-byte Mint layout, and authority tags are validated.
- RiskEngine requires matching mint evidence for both classic SPL Token and Token-2022; program ID alone cannot bypass the final gate.
- Discovery WATCH/BLOCKED gate runs before RugCheck/holder/AI/scoring.
- Paper entry refreshes owner/extension evidence immediately before deterministic RiskEngine evaluation.
- AI cannot override a gate; all existing independent risk controls remain.
- No new thresholds, migrations, live signing, transaction construction, Jupiter/Jito execution or broadcast.

## Validation

- Unit and end-to-end tests authored; NOT RUN in this authoring environment.
- python3 tools/ci.py: NOT RUN; no claim of PASS.
- GitHub Actions must be checked against the final head SHA.
- No production-readiness claim.

## Rollback

Revert PR #50. No schema migration or persistent side effect.
