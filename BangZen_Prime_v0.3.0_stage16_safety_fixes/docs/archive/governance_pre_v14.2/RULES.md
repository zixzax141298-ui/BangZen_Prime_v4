# BANGZEN PRIME — Engineering Rules

**Authority:** `AI_RULES.yaml` is the machine-readable constitution. This document explains how contributors must apply it. In a conflict, stop and follow the authority order in `AI_RULES.yaml`.

## 1. Mission and success criteria

Build a Solana token-intelligence system that seeks positive net expectancy while minimizing avoidable losses. Profit is uncertain; no strategy, model, test, or backtest may promise returns.

Success is measured by evidence quality, net-of-cost performance, drawdown control, operational reliability, and reproducibility—not raw signal count.

## 2. Mandatory operating boundary

- Default to read-only data collection and paper trading.
- Live trading, private-key signing, and transaction broadcast remain locked.
- A general request to improve performance is not authorization to enable live execution.
- No private key, seed phrase, wallet secret, or production credential may be added to source control.
- Risk/Safety is deterministic and owns the final veto. AI recommendations cannot override it.
- Missing, stale, partial, or contradictory safety evidence must never be interpreted as safe.

## 3. Evidence before decisions

Every material decision must identify its evidence references, provider/source, observation time, freshness, completeness, validation state, and reason codes.

Use explicit states:
- `VERIFIED`: validated for the stated scope only.
- `PARTIAL`: incomplete coverage.
- `UNAVAILABLE`: not obtained or not usable.
- `CONFLICTED`: sources or records disagree.
- `REJECTED`: malformed, invalid, or failed validation.

A provider's response is not proof of safety. Historical pagination exhaustion is not proof of complete chain, token, or wallet history. Never substitute zero or a favorable default for missing data.

## 4. AI Manager and strategy modules

- AI may reason only over validated, versioned evidence supplied by the Data Gateway.
- AI must not call providers directly, access API keys, read wallet secrets, sign, or broadcast.
- AI may select at most one registered and allowlisted strategy/defensive module for a decision cycle.
- The selected module must declare its capability, required evidence, failure behavior, and output schema.
- AI output is advisory. A recommendation such as `BUY_CANDIDATE` is not an order or execution authorization.
- If required evidence is unavailable or conflicts with a hard gate, return `HOLD` or `SKIP` with reason codes. Never hallucinate missing facts.
- Scores are rankings or model outputs, not probabilities unless calibrated and independently validated as probabilities.

## 5. Architecture boundaries

Dependencies point inward:

| Area | Responsibility |
|---|---|
| `bangzen_prime/domain` | Pure domain models, invariants, deterministic calculations |
| `bangzen_prime/application` | Use cases, orchestration, ports, policies |
| `bangzen_prime/infrastructure` | Provider adapters, persistence, HTTP, queues, resilience |
| `bangzen_prime/execution` | Execution boundary; currently simulated/read-only only |
| `bangzen_prime/interfaces` | CLI and user-facing interfaces |
| `bangzen_prime/bootstrap.py` | Composition root; wires concrete implementations |
| `tests/` | Unit, integration, and end-to-end verification |
| `scripts/` | Reproducible developer and maintenance tools |
| `docs/` | Architecture, contracts, runbooks, decisions, and ledgers |
| `native/` | Native/Rust components with explicit Python boundary contracts |

Rules:
- Domain code must not perform network, filesystem, or database I/O.
- Provider-specific implementation belongs in infrastructure adapters.
- Credentials are injected only into provider adapters through the approved configuration boundary.
- AI receives normalized evidence, never raw credentials or unrestricted provider clients.
- Risk/Safety must remain independently testable and must not depend on AI availability.
- Avoid duplicate implementations and circular imports.
- Do not move existing code merely to make the tree look different. Relocation requires a dedicated migration PR with import, packaging, and rollback tests.

## 6. Risk and performance accounting

- Evaluate net outcomes after entry/exit fees, slippage, price impact, priority fees/tips, partial fills, and realistic exit assumptions.
- Distinguish gross PnL from net PnL.
- Backtests must avoid look-ahead bias, survivorship bias, and data leakage.
- Report sample size, time range, data coverage, excluded records, assumptions, and uncertainty.
- Never change risk thresholds, position sizing, SL/TP behavior, or safety filters without explicit owner approval and tests.
- Do not loosen filters simply to increase the number of signals.

## 7. Engineering workflow

Each PR must:
1. Have one clearly stated objective and bounded scope.
2. State the base branch and base commit.
3. Describe changed files and behavioral impact.
4. Add or update positive, negative, boundary, and failure-path tests as appropriate.
5. Preserve all existing tests; never delete, skip, weaken, or rewrite assertions merely to get a green result.
6. Include a Change Ledger with actual commit/base/head identifiers, validation commands, results, and known limitations.
7. Document migrations, compatibility, rollback, and operational impact where relevant.
8. Remain unmerged until the owner approves it.

Prefer small, additive, reversible PRs. Governance, strategy, provider, and execution changes must not be bundled without a compelling and documented dependency.

## 8. Definition of DONE

A task is not DONE unless:
- Scope and acceptance criteria are met.
- Relevant tests and checks were actually executed.
- `python3 tools/ci.py` is fully green when that gate exists and is applicable.
- Security and regression checks are recorded.
- Documentation and Change Ledger are updated.
- No unresolved critical safety issue remains.

If the required tool or dependency is absent, inaccessible, or not run, report `BLOCKED` or `NOT_RUN`. Never claim a pass, production readiness, or completion based on intention, code inspection alone, or a partial check.

## 9. Status reporting

Use precise terms:
- **PASS:** exact check ran and passed.
- **FAIL:** exact check ran and failed.
- **NOT RUN:** check was not executed.
- **BLOCKED:** check could not execute due to a missing prerequisite.
- **UNAVAILABLE:** required data or evidence could not be obtained.
- **PARTIAL:** some, but not all, requirements are satisfied.

A report must separate implementation status, test status, CI status, review status, and merge status.

## 10. Required references

- Constitution: `AI_RULES.yaml`
- Security policy: `SECURITY.md`
- Agent operating instructions: `AGENTS.md`
- Architecture: `docs/ARCHITECTURE.md`
- Testing: `docs/TESTING.md`
- Operations: `docs/RUNBOOK.md`
- Configuration: `docs/CONFIGURATION.md`
- Governance folder map: `docs/governance/README.md`
