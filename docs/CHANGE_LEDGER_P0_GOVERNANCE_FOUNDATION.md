# Change Ledger — P0 Governance Foundation

## Objective

Restore a clear, repository-wide policy hierarchy and document ownership boundaries before implementing the AI Manager in a later PR.

## Base and branch

- Repository: `ripsterxiui98-coder/BangZenPrime-v3`
- Base branch: `main`
- Base SHA: `296a13ccee27eb57f0dd7e363e95cf4474828139`
- Working branch: `chore/p0-governance-foundation`
- Head SHA: To be recorded after all PR commits are created.

## Files added

- `AI_RULES.yaml` — machine-readable constitution, safety invariants, evidence and AI decision contract, engineering gates.
- `RULES.md` — contributor standards and Definition of DONE.
- `AGENTS.md` — mandatory AI agent workflow and restrictions.
- `SECURITY.md` — threat model, secrets, provider, AI, execution, storage, and incident policy.
- `docs/governance/README.md` — policy hierarchy and repository folder ownership map.

## Non-goals

- No production source code, strategy thresholds, risk limits, or runtime configuration changed.
- No AI Manager, weapon selection, BUY/SKIP/HOLD implementation, or JSON runtime contract implementation.
- No live trading, signing, transaction construction, or broadcast capability added.
- No existing source or documentation paths moved or deleted.

## Validation

- Repository tree and existing architecture, testing, runbook, configuration, and security documentation inspected through GitHub.
- YAML parsing, markdown lint, tests, and `python3 tools/ci.py`: NOT RUN in this authoring environment.
- No test, CI, or security-scan pass is claimed.

## Known limitations

- The current repository does not contain `tools/ci.py`; the policy names it as a required gate when restored/available. Until then, the documented test runner and available checks must be used, and the missing gate must be reported as BLOCKED rather than treated as passed.
- Existing `docs/SECURITY.md` remains the implementation-specific security inventory. Root `SECURITY.md` is the policy authority; differences must be reconciled rather than silently ignored.
- Existing docs are intentionally not relocated in this PR to avoid broken links and unrelated churn.

## Review checklist

- [ ] Owner reviews and approves policy contents.
- [ ] YAML is parsed by a real YAML parser.
- [ ] Documentation references and policy precedence are checked.
- [ ] PR remains unmerged until owner approval.
