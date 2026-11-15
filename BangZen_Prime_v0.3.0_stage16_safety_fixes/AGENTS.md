# BANGZEN PRIME — AI Coding Agent Instructions

**Version:** 14.2 | **Mandatory** | **Primary policy:** `AI_RULES.yaml`

## 1. Role and reading

Act as a Lead Software Engineering Agent. Before editing, read `AI_RULES.yaml`,
`SECURITY.md`, `RULES.md`, this file, `BANGZEN_STRATEGIC_CONSTITUTION.md`,
relevant architecture docs, source files, callers, tests, and `tools/ci.py`.

Inspect branch, base SHA, worktree, protected files, and existing tests.
Do not overwrite unrelated changes or perform destructive Git operations.

## 1a. Master Blueprint 2026 (binding structure)

Read `BANGZEN_PRIME_MASTER_BLUEPRINT_2026.md` and `docs/STRUCTURE_MAPPING_2026.md` before adding
capability. Place new code in the mapped location. Do not add a folder outside the mapping, a
second provider adapter, or a second notifier without owner approval. Never weaken a test to
obtain green CI (blueprint section 20.1). HALT.flag is IMPLEMENTED (risk/emergency_stop.py, stage 1); keep it fail-closed.

## 2. AI invocation contract

Implement event-driven research. Enqueue AI only after a configured,
confirmed transaction lifecycle event:
- Confirmed buy.
- Confirmed sell.
- Confirmed partial fill.
- Confirmed position-state change.

Persist raw event evidence before enqueueing. Reject unconfirmed intents and
deduplicate using stable event ID, request ID, and evidence snapshot hash.
AI must not run synchronously in the execution path. If unavailable, keep the
research job queued for delayed analysis.

## 3. Input minimization

Build a versioned immutable snapshot containing approved market evidence:
token/pool/venue, event time, token age, market-cap estimate and source,
holder concentration, evidenced dev/insider/bundler associations, wallet
cluster evidence and coverage, liquidity and lock verification, volume,
transaction activity, tax observations, and pre/post-event market snapshots.

Do not include credentials, wallet secrets, PnL, net profit, win/loss labels,
financial outcome labels, or prompts to evaluate financial outcomes.
Do not turn missing cluster evidence into a claim that no cluster exists.

## 4. AI role boundary

AI only researches and summarizes evidence. It cannot make trading
decisions, evaluate financial performance, calculate or discuss net profit,
wins or losses, authorize execution, modify risk or strategy policy, or
access wallet signing/broadcast capabilities.

## 5. Nine-route fallback

Implement nine independently configurable provider slots behind one common
adapter interface. Use one active provider per job by default. Preserve the
same request ID and evidence snapshot hash across fallback attempts.
Classify missing credentials, quota, rate limits, timeouts, provider errors,
authentication failures, invalid responses, and policy violations.

If all providers fail, persist the queued job. Never retry indefinitely.
Do not treat model agreement as evidence.

## 6. Research reputation

Implement a deterministic, auditable research-quality evaluator outside
the model. Evaluate evidence-reference validity, claim support, independent
factual consistency, timestamps, freshness, completeness, uncertainty,
schema/policy compliance, reproducibility, and later independent confirmation.

Never use PnL, net profit, wins, losses, returns, or trade outcomes as scoring
inputs. Require a minimum independently verified sample size. Keep
provider/model/prompt/schema versions separate. Reputation may adjust route
priority only; it must not grant authority or bypass health/security checks.
A provider is replaceable; do not implement identity or irreplaceability claims.

## 7. Tests

Preserve existing tests. Add tests for:
- Confirmed buy/sell/partial-fill/position-change triggers.
- No trigger on unconfirmed intent.
- Event persistence before enqueue.
- Deduplication and immutable snapshot reuse.
- AI outage and delayed queue recovery.
- Single active provider and ordered fallback.
- Quota, rate-limit, timeout, authentication, and malformed output.
- Input redaction and prohibited financial fields.
- Evidence citation and independent validation.
- Reputation scoring and minimum sample size.
- No reward from financial outcome fields.
- Policy violations, quarantine, and owner-controlled reinstatement.
- FAST PATH independence from AI.

Use mocks and deterministic fixtures. Never use real credentials or submit
real transactions in tests.

## 8. CI and change control

Run `python3 tools/ci.py` with the required profile. Report exact results and
checks not run. Termux LOCAL PASS is not FULL CI GREEN.

Record base/head SHA, changed paths, rationale, tests actually executed,
security checks, not-run checks, limitations, and rollback. Never claim
DONE without required evidence. Owner approval is required for protected
policy, risk, security, credential, and live-execution changes.
