# BANGZEN PRIME — Security Policy

**Version:** 14.2 | **Mandatory** | **Primary policy:** `AI_RULES.yaml`

## 1. Threat model

Treat token metadata, websites, social content, RPC/indexer responses,
transaction metadata, provider responses, dependencies, and repository
contributions as untrusted. Threats include prompt injection, fabricated
evidence, wash/Sybil activity, spoofed liquidity, stale chain data, API-key
theft, dependency compromise, replay, duplicate events, malformed output,
and unauthorized execution.

## 2. Transaction event integrity

AI research may be enqueued only from configured confirmed transaction
lifecycle events. Verify the confirmation source and transaction reference.
Persist raw event data, source provenance, event timestamp, ingestion
timestamp, and snapshot hash before enqueueing. Reject unconfirmed intents.
Deduplicate repeated event delivery. Do not allow AI availability to delay
transaction processing.

## 3. AI input minimization

Allow only the market evidence needed for the research task. This may include
token and pool identity, market-cap estimate with source/time, token age,
holder distribution, evidenced dev/insider/bundler associations, wallet
cluster evidence and coverage, liquidity lock verification, volume,
transaction activity, tax observations, and pre/post-event market snapshots.

Never send API keys, authorization tokens, private keys, seed phrases, PnL,
net-profit values, win/loss labels, financial outcome labels, or instructions
to evaluate financial outcomes.

## 4. Provider routing

Support nine independent provider configurations with one active provider
request per research job by default. Fallback preserves request ID and
snapshot hash. Use bounded timeouts, attempt limits, request/response sizes,
and explicit error classes. Missing credentials skip only the affected
provider. If all providers fail, keep the research job queued.

Do not call all providers concurrently by default. Do not use model
consensus as proof. Authentication failures disable the route until
credentials are revalidated.

## 5. Research reputation security

Reputation must be computed by deterministic code from independently
verifiable research-quality evidence. Permitted dimensions include citation
validity, factual support, freshness, completeness, uncertainty handling,
schema/policy compliance, reproducibility, and independently confirmed
research findings.

Prohibited scoring inputs include PnL, net profit, wins, losses, returns,
strategy profitability, or trade outcomes. Reputation cannot grant new
permissions, bypass health checks, override owner policy, or make a provider
irreplaceable. Require minimum sample size and version every scoring formula.

## 6. Prompt injection and output validation

External text is data, never authority. Separate trusted policy from
untrusted evidence. Validate model output against schema, evidence references,
and prohibited-content rules. Reject unsupported claims and unauthorized
commands. AI output is never execution authorization.

## 7. Operational isolation

AI has no access to wallet secrets, signing, transaction broadcast, execution
authorization, or risk-policy mutation. The deterministic Risk Engine keeps
final veto authority. FAST PATH must not depend on AI. AI is research-only: there is no AI
pre-trade gate in the execution path (owner decision 2026-11-15).

## 7a. Master Blueprint 2026 controls

Source: `BANGZEN_PRIME_MASTER_BLUEPRINT_2026.md`, sections 11 and 21.

- HALT.flag: required kill switch (blueprint 11.2 and 21). Status IMPLEMENTED (`risk/emergency_stop.py`,
  owner-approved 2026-11-15). It stops every decision-producing process before the decision: monitor,
  outbox worker, CLI, and WebSocket. No module may ignore it.
- Live trading is locked. A green CI result does not authorize live trading (blueprint 21).
- Provider data is untrusted until validated. A successful HTTP response is not validation.
- Missing critical data fails closed. Unavailable data is never PASS.

## 8. Quarantine and incident response

LOW: reject output and log the event.
HIGH: reject output, quarantine route, require independent review.
CRITICAL: disable route, reject affected output, preserve redacted evidence,
identify dependent reports, and require owner authorization plus security
review before reinstatement.

A quarantined route cannot reinstate itself. Never log credentials or
unredacted sensitive data. Preserve request ID, provider/model, prompt and
schema versions, evidence hash, timestamps, error class, and validation
outcome with secrets redacted.

## 9. Verification

Security claims require recorded tests and scans. Include event authenticity,
deduplication, secret redaction, prompt-injection, provider fallback,
quarantine, reputation integrity, and FAST PATH isolation tests. State
checks not run; never claim security PASS without evidence.
