# BANGZEN PRIME Governance Package — v14.2

## Included documents

- `AI_RULES.yaml` — machine-readable AI authority and event/research contract.
- `RULES.md` — mandatory system-wide rules.
- `AGENTS.md` — coding-agent requirements.
- `SECURITY.md` — threat model and security controls.
- `BANGZEN_STRATEGIC_CONSTITUTION.md` — system blueprint and development roadmap.

## Design summary

AI is called after confirmed buy, sell, partial-fill, or position-state
events. Raw evidence is persisted first. The research job uses a minimized,
immutable snapshot and is processed by one active AI provider at a time.
Nine configurable provider routes support priority fallback. If all providers
are unavailable, the job remains queued for later analysis.

AI is strictly a market research analyst. It cannot make trading decisions,
calculate or discuss net profit, analyze wins/losses or trade outcomes,
modify risk/strategy policy, or access wallet signing/broadcast capabilities.

A deterministic Research Reputation evaluator may score research quality
using citation validity, factual support, freshness, completeness,
uncertainty handling, reproducibility, and independent confirmation.
Financial outcomes must never be scoring inputs. Reputation may adjust
provider priority but cannot grant authority or make a provider irreplaceable.

## Policy versus implementation

These files define policy. They do not prove that repository code already
enforces it. Implementation and tests are still required for transaction
event confirmation, event persistence, deduplication, queue recovery,
single-provider fallback, schema validation, research reputation, quarantine,
secret redaction, and FAST PATH isolation.

## Adoption

Inspect the repository and existing governance first. Compare documents,
resolve conflicts, preserve existing tests and user changes, implement
enforcement incrementally, run required CI, and record a Change Ledger.
Do not blindly overwrite repository files or claim implementation is done.

## Master Blueprint 2026 (binding)

`BANGZEN_PRIME_MASTER_BLUEPRINT_2026.md` sets the mandatory structure and workflow. Where it
conflicts with the constitution or `AI_RULES.yaml`, those prevail and the conflict is reported.
Structure mapping: `docs/STRUCTURE_MAPPING_2026.md`. Alignment record:
`docs/CHANGE_LEDGER_BLUEPRINT_2026_ALIGNMENT.md`.
