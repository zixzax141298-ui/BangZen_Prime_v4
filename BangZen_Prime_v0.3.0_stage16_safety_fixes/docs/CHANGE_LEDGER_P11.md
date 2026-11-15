# Change Ledger — P11 Portable Validation and README

## Objective
Make the P10 gate usable across Termux, VPS/Linux, and GitHub Actions; separate portable
development dependencies from platform-specific security tools; document setup and BYOK.

## Base and head
- Base branch: `ci/p10-enforce-institutional-quality-gate`
- Base commit: `944a077917fa24a9f41f3072224b3c51d2af37d6`
- Head branch: `ci/p11-portable-validation-readme`
- Pre-ledger implementation head: `f9ad18d777cd43bae93a5fa41e8081b5ff5bcc76`
- The final head SHA is recorded in the live GitHub PR metadata because this ledger commit itself advances the branch.

## Changes
- Add `termux`, `vps`, `github`, `full`, and `auto` validation profiles.
- Add repository-aware checks, explicit statuses, and JSON report.
- Keep stdlib unittest as the canonical suite; avoid duplicate pytest execution.
- Make Black, Ruff, Mypy, Bandit, Semgrep, and pip-audit mandatory in full profiles.
- Run Cargo checks only when native Rust manifest exists.
- Remove Safety API-key dependence from mandatory gate; keep Safety supplemental.
- Split portable `dev` and Linux/VPS `security` extras.
- Add README covering Termux, VPS, BYOK, Strix, CI, and safety boundaries.
- Ensure pull-request workflow also runs on the stacked P11 base branch.

## Safety impact
No strategy thresholds, risk limits, wallet access, signing, broadcast, or live trading
behavior changes. No secrets added. No tests removed, skipped, or weakened.

## Validation evidence
- Existing repository files inspected through GitHub before authoring.
- Local full repository tests: NOT RUN in this session.
- `python3 tools/ci.py`: NOT RUN in this session.
- GitHub Actions: pending; no completed run has been verified.
- Strix scan: NOT RUN; this PR prepares documentation and validation only.

## Known limitations
- Termux is a portable Python baseline, not complete security clearance.
- Full profiles require all declared tools.
- Strix requires supported Linux/Docker and operator-supplied model credentials.
- Runner provisioning failures before job steps execute remain infrastructure blockers.

## Merge gate
Do not merge until GitHub checks execute, portable profile is run on Termux or equivalent,
and full profile is run on VPS/Linux. No green CI or production-readiness claim is made.
