# BANGZEN PRIME — Strategic Constitution and Blueprint

**Version:** 14.2  
**Mission:** Adaptive Solana Market Intelligence and Trading Infrastructure

## 1. Core principles

- Evidence must be persisted before AI research.
- AI is an event-driven research analyst, not a trading authority.
- One AI provider is active per research job by default.
- Nine independently configurable provider routes support fallback.
- Deterministic components own strategies, risk, execution, and accounting.
- FAST PATH must never wait for AI.
- Research history must be reproducible and auditable.

## 2. FAST PATH

Market/RPC events
-> Persist raw event and provenance
-> Normalize and validate
-> Deterministic strategy engine
-> Deterministic constraints
-> Risk Engine veto
-> Authorized execution interface
-> Confirmed transaction lifecycle event

No synchronous AI dependency is permitted in this path.

## 3. AI invocation: confirmed transaction events

The AI research queue is triggered after configured confirmed events:
- Confirmed buy transaction.
- Confirmed sell transaction.
- Confirmed partial fill.
- Confirmed position-state change.

Do not trigger from an unconfirmed order intention or an unverified interface
state. Persist the raw event and source references first. Use event ID,
request ID, and evidence snapshot hash for deduplication and replay.

The research snapshot may describe the market state surrounding the event:
market-cap estimate, token age, venue/launch stage, top-holder concentration,
dev/creator-associated share, insider-associated share, bundler-associated
share, wallet-cluster evidence, liquidity and lock verification, volume,
transaction counts, tax observations, and pre/post-event market snapshots.

Every metric needs source, timestamp, freshness, completeness, and coverage.
For example, if no coordinated wallet cluster is detected, report
`NOT_DETECTED_WITH_COVERAGE_LIMITS`; do not claim that no syndicate exists
unless the evidence actually supports that conclusion.

AI may compare observations across events and describe recurring patterns.
It must not infer that a configuration is profitable or recommend a trade.
A high holder concentration combined with no detected cluster is a research
observation, not proof of safety or a prediction of financial success.
Incomplete liquidity-lock evidence must remain explicitly incomplete.

## 4. SLOW PATH

Confirmed event
-> Research event selector
-> Immutable minimized snapshot
-> Deduplication and persistent queue
-> Single-active-provider router
-> AI research request
-> Independent schema/evidence/policy validation
-> Research archive
-> Research reputation evaluator
-> Authorized downstream research consumer

If every provider is unavailable, retain the job and retry later under
bounded scheduling. Do not lose events and do not block FAST PATH.

## 5. Nine provider routes, one active AI

Configure nine provider slots. Initial examples may include OpenAI,
Anthropic, xAI, Google, DeepSeek, Qwen, Mistral, and two additional
owner-selected providers. Provider/model identifiers must be verified
against the actual integration; placeholders are not working adapters.

Use configured priority and health. Only one provider request is active per
job by default. Fallback preserves request ID and snapshot hash.
Provider agreement is not truth and cannot authorize an action.

## 6. Research-only boundary

AI can analyze market evidence and summarize:
- Token/pool and launch context.
- Holder concentration and wallet relationships.
- Liquidity and lock-state evidence.
- Volume and transaction behavior.
- Tax observations.
- Pre-event/post-event changes.
- Data quality, anomalies, uncertainty, and hypotheses.

AI cannot issue trading commands, calculate or discuss net profit, analyze
wins/losses or trade outcomes, evaluate strategy profitability, modify risk
or strategy settings, or access signing/broadcast capabilities.

Do not include PnL or financial outcome labels in AI input or research
reputation scoring.

## 7. Research Reputation & Reward System

The system may maintain a quality and reliability score for each
provider/model/prompt/schema version. The evaluator is deterministic,
independent from the model, versioned, and auditable.

Permitted quality evidence:
- Citation resolves to the correct source.
- Claim is supported by source evidence.
- Findings match independently verified records.
- Timestamp, freshness, and completeness are correct.
- Uncertainty and limitations are appropriately reported.
- Schema and policy are followed.
- Findings are reproducible.
- A previously reported pattern is independently observed again in later
  research with adequate evidence.

A reward may improve provider selection priority after a minimum sample
size and independent verification. It cannot grant additional permissions,
bypass availability/security checks, or guarantee permanent selection.
Scores must be separated by provider, model, prompt version, and schema
version. A provider is a replaceable service, not a persistent person or
irreplaceable intelligence.

No reward or penalty may depend on net profit, PnL, wins, losses, returns,
or trade outcomes. Those belong to separate deterministic evaluation
systems and are not AI research inputs.

## 8. Experience Journal

Begin at the first infrastructure stage. Store immutable raw events,
provenance, snapshots, AI request metadata, accepted/rejected reports,
provider failures, validation outcomes, reputation evidence, and human
reviews. Preserve event time and ingestion time. Never replace raw evidence
with AI summaries.

## 9. Separate deterministic subsystems

- Strategy Engine: registered, versioned strategy logic.
- Risk Engine: deterministic final veto.
- Execution: paper by default; live locked pending separate approval.
- Accounting: deterministic financial ledger and cost attribution.
- Evolution Lab: final major development stage; deterministic evaluation
  of experiments and controlled promotion.

AI must not perform the accounting or financial-performance evaluation.

## 10. Development roadmap

PR-01 — Solana Environment Gateway and durable event archive  
PR-02 — Real-Time Market Intelligence  
PR-03 — Wallet and Entity Intelligence  
PR-04 — Adaptive Strategy Engine  
PR-05 — Execution and Routing Engine (paper/simulation first)  
PR-06 — Risk and Capital Survival Engine  
PR-07 — Unified Paper/Live Architecture (live locked)  
PR-08 — Deterministic Total System Accounting  
PR-09 — Strategy Evolution Laboratory

Event persistence, post-transaction research queue, and audit logging begin
early; they are not postponed to PR-09.

## 11. Governance

`AI_RULES.yaml` is the primary AI authority contract. `RULES.md`,
`AGENTS.md`, and `SECURITY.md` must remain consistent. Protected changes
require owner approval. Every PR requires tests, CI evidence, limitations,
and a Change Ledger. No unsupported DONE or security claims.
