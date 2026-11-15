# BANGZEN PRIME — Mandatory System Rules

**Version:** 14.2 | **Status:** Mandatory | **Primary policy:** `AI_RULES.yaml`

## 1. Mission

BANGZEN PRIME is a modular Solana market-intelligence and trading
infrastructure. AI is an event-driven market research analyst only.
Operational decisions remain deterministic and outside AI authority.

## 2. Exact AI invocation rule

AI research is enqueued after a configured, confirmed transaction lifecycle
event, including:
- Confirmed buy transaction.
- Confirmed sell transaction.
- Confirmed partial fill.
- Confirmed position-state change.

Do not invoke AI for an unconfirmed transaction intention or duplicate event.
Persist the original event and its evidence before enqueueing AI research.
Use stable event IDs, request IDs, and evidence snapshot hashes.

AI is not required to run synchronously before or during execution. The FAST
PATH must complete independently. If AI is unavailable, preserve the job
for later research.

## 3. Research snapshot

The AI may receive minimized, timestamped evidence such as:
- Token, pool, venue, and launch-stage identity.
- Market-cap estimate, source, and observation time.
- Token age.
- Top-holder concentration and holder distribution.
- Dev/creator-associated, insider-associated, and bundler-associated
  concentration where independently evidenced.
- Wallet-cluster or coordinated-activity evidence and coverage limitations.
- Liquidity amount, lock/burn state, and verification coverage.
- Buy/sell activity, transaction counts, and volume.
- Tax observations and their source or simulation method.
- Pre-event and post-event market snapshots.

Do not present an unverified label such as "syndicate" as a fact. Report
whether a cluster was detected, not detected, or could not be assessed, and
state the data coverage.

Exclude API keys, private keys, seed phrases, PnL, net-profit values,
win/loss labels, financial outcome classifications, and prompts to judge
whether a transaction was financially successful.

## 4. AI authority

AI may describe evidence, compare sources, identify patterns, state
uncertainty, and propose further data collection.

AI must not:
- Make BUY, SELL, HOLD, EXECUTE, or transaction approval decisions.
- Calculate, discuss, or evaluate net profit or financial returns.
- Analyze wins, losses, or trade outcomes.
- Evaluate strategy profitability.
- Modify strategy parameters, risk limits, or policies.
- Access wallet secrets, signing, or broadcast methods.

AI findings are research reports, not commands or authorization.

## 5. One active provider and nine routes

Support nine independently configured provider routes. Use one active
provider per research job by default. Select by configured priority and
eligible health. On quota, rate-limit, timeout, or availability failure,
try the next eligible provider within the deadline and attempt limit.

Fallback must reuse the same request ID and immutable evidence snapshot.
Do not call all providers concurrently by default. Do not use model majority
as proof. If all providers fail, keep the job queued.

## 6. Research reputation and reward

Maintain a versioned research-quality score for each provider/model/prompt
combination. Score only verifiable research quality:
- Evidence references resolve correctly.
- Claims are supported by cited source records.
- Facts match independently verified evidence.
- Timestamps, freshness, and completeness are reported correctly.
- Uncertainty and limitations are handled honestly.
- Reports follow schema and policy.
- Findings are independently confirmed and reproducible.
- Previously identified patterns are useful in later research when
  independently re-observed.

Do not score or reward AI based on profit, PnL, wins, losses, financial
returns, or trade outcomes. Do not send those labels to AI.

Rewards may improve provider selection priority only after a minimum
independently verified sample size. They must never grant additional
permissions, bypass provider health checks, or override policy. Keep scores
separate by provider, model, prompt version, and report schema version.
A provider/model is a replaceable service identity, not a persistent person.
Never claim that a provider is irreplaceable.

## 7. Evidence integrity

Every material claim must reference source evidence. Missing is not zero,
false, or safe. Partial data remains PARTIAL; conflicting data remains
CONFLICTED. Raw evidence is immutable or versioned and is never replaced
by AI summaries.

## 8. FAST PATH and SLOW PATH

FAST PATH: ingestion, persistence, normalization, deterministic strategy
processing, constraints, Risk Engine veto, and authorized execution.
It has no AI dependency.

SLOW PATH: confirmed event queue, snapshot, provider routing, research,
independent validation, report archive, reputation evaluation, and
downstream research delivery.

## 9. Master Blueprint 2026 alignment (binding)

- Document: `BANGZEN_PRIME_MASTER_BLUEPRINT_2026.md`. Precedence: AI_RULES.yaml, then the
  constitution, then this file. The blueprint cannot weaken AI, risk, or safety rules.
- Structure: new capability follows `docs/STRUCTURE_MAPPING_2026.md`. No new top-level folder
  and no duplicate provider or notifier without owner approval.
- Watch-only and paper only. Telegram is signal-only. Transaction signing is prohibited.
- Fail closed. Missing, stale, partial, or conflicting critical data is UNAVAILABLE, PARTIAL,
  or CONFLICTED and never PASS. Missing values are never stored as zero.
- Net PnL includes entry and exit fees, network fees, entry and exit slippage, price impact, and
  other costs. Performance analytics are deterministic. AI does not perform them.
- HALT.flag (blueprint sections 11.2 and 21) is required and currently NOT IMPLEMENTED. Report
  its status honestly in every change until it is implemented.
- CI: `python3 tools/ci.py` is the required gate. Failing tests are never skipped or bypassed to
  obtain green. Blueprint tools not yet listed in `tools/ci.py` are reported NOT_RUN.

## 10. Engineering, security, and governance

Preserve all existing tests. Add deterministic tests for event triggers,
deduplication, fallback, queue recovery, output validation, reputation
scoring, prohibited inputs, and FAST PATH independence.

Never fabricate tests or CI results. Termux LOCAL PASS is not FULL CI GREEN.
Protected policy, security, risk, credential, and live-execution changes
require explicit owner approval. Record every change in the Change Ledger.
