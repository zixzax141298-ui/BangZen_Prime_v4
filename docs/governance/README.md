# Governance and Repository Layout

This folder contains governance maps, decision records, and process documentation. Root policy files remain the authoritative entry points.

## Policy hierarchy

1. `AI_RULES.yaml` — machine-readable constitution and non-negotiable project invariants.
2. `SECURITY.md` — security policy and threat boundaries.
3. `RULES.md` — engineering standards, change control, and Definition of DONE.
4. `AGENTS.md` — operational instructions for AI agents and contributors.
5. `docs/` — explanatory architecture, contracts, testing, runbooks, and records.
6. Source code and tests — implementation; they do not override policy.

If documents conflict, stop the affected work and request owner clarification. Do not silently choose the more permissive interpretation.

## Existing repository map

| Path | Owns | Must not own |
|---|---|---|
| `bangzen_prime/domain/` | Pure domain types, invariants, deterministic calculations | Network, database, provider clients |
| `bangzen_prime/application/` | Use cases, orchestration, ports, application policies | Provider credentials or low-level transport details |
| `bangzen_prime/infrastructure/adapters/` | External provider and transport adapters | AI policy decisions or final risk veto |
| `bangzen_prime/infrastructure/persistence/` | Database access, migrations, repositories | Strategy-specific business policy |
| `bangzen_prime/execution/` | Execution boundary; current implementation remains simulated/locked | AI signing authority or bypass of Risk/Safety |
| `bangzen_prime/interfaces/` | CLI and user-facing interfaces | Provider secrets or duplicated domain logic |
| `bangzen_prime/bootstrap.py` | Composition root and dependency wiring | Business rules hidden in wiring code |
| `config/` | Non-secret configuration templates and defaults | Production secrets |
| `tests/unit/` | Isolated component tests | Real network calls or real wallet secrets |
| `tests/integration/` | Cross-component and persistence tests | Production endpoints or funds |
| `tests/e2e/` | End-to-end behavior using fakes/simulation | Live transactions |
| `scripts/` | Reproducible maintenance and developer commands | Unreviewed production behavior |
| `native/` | Rust/native acceleration with explicit boundary contracts | Duplicated Python business policy |
| `docs/` | Architecture, API contracts, operations, decisions, ledgers | Secrets or unverified claims |
| `reports/` | Generated test/coverage/analysis artifacts | Source-of-truth policy |

## Intended documentation organization

New documentation should use these folders when there is enough content to justify them:

- `docs/architecture/`: architecture diagrams and boundary explanations.
- `docs/decisions/`: Architecture Decision Records (ADRs), one decision per file.
- `docs/runbooks/`: operational and incident procedures.
- `docs/governance/`: policy map, contribution workflow, and governance decisions.
- `docs/ledgers/`: consolidated change records only if the existing root-level ledger convention is formally migrated.

Existing documents at `docs/` root remain in place. Do not mass-move them as part of a governance PR. A later documentation-only migration may introduce redirects and update all references.

## Naming and ownership rules

- Use descriptive lowercase snake_case for Python modules and SQL migrations.
- Keep one concern per module and one objective per PR.
- Mirror source package paths in tests where practical.
- Keep provider-specific modules grouped by provider/protocol under infrastructure adapters.
- Keep SQL migrations sequential and immutable after release; add a new migration for schema changes.
- Do not create a new folder for a single speculative file unless it clarifies ownership.
- Every new operational or architectural decision must link to the relevant policy and Change Ledger.

## Change workflow

1. Inspect current tree and policy files.
2. Define the smallest safe scope and non-goals.
3. Create a focused branch and PR.
4. Add tests and documentation for behavior changes.
5. Record exact validation results and limitations.
6. Request owner review; never merge without approval.
