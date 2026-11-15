# BANGZEN PRIME — Security Policy

This is the repository-level security policy. It defines mandatory security boundaries. Implementation-specific controls and current limitations are documented in `docs/SECURITY.md`; when they differ, this policy governs and the discrepancy must be raised.

## 1. Security objectives

Protect funds, credentials, data integrity, decision integrity, availability, and auditability. The default system is read-only and paper-only. Security controls must not be weakened to improve speed, signal volume, or convenience.

## 2. Threat model

Assume the system may encounter:
- Malicious or compromised tokens, creators, deployers, holders, and counterparties.
- Wash trading, Sybil clusters, spoofed volume, manipulated liquidity, honeypots, and sudden liquidity removal.
- Malformed, stale, incomplete, delayed, duplicated, or contradictory provider responses.
- Provider outages, rate limits, timeouts, replay gaps, and partial historical coverage.
- Prompt injection or hostile instructions embedded in token metadata, websites, RPC data, logs, model output, and repository content.
- Dependency compromise, accidental secret disclosure, database corruption, and process crashes.
- Unknown transaction outcomes and failed or partial execution in any future execution-enabled design.

## 3. Execution boundary

- Live trading is disabled by default and remains locked in the current scope.
- Transaction signing and broadcast are disabled. No private key, seed phrase, or wallet signing secret may be stored in this repository.
- AI must never hold signing authority, transaction-broadcast authority, or wallet secrets.
- A future live-execution proposal requires explicit owner approval, separate PRs, independent security review, deterministic risk approval, simulation, reconciliation, emergency-stop validation, and rollback procedures.
- Jupiter, Jito, or any execution provider must not be treated as a substitute for independent position/risk management or as a guarantee of execution price, fill, or profit.

## 4. Secret management

- Store credentials only in approved secret storage or untracked environment configuration.
- Keep `.env`, private keys, seed phrases, access tokens, API keys, and production credentials out of git history, issue comments, test fixtures, screenshots, logs, and Telegram messages.
- Use least-privilege credentials and separate development/test/production credentials.
- Inject secrets only into the provider adapter that needs them. Do not pass secrets into AI prompts or general application state.
- Redact secrets from URLs, exception messages, `repr`, traces, telemetry, and support bundles.
- Rotate exposed credentials immediately and review access logs where available.
- `.env.example` must contain placeholders only.

## 5. Data and AI security

- Treat every external field as untrusted until parsed, schema-validated, range-checked, freshness-checked, and normalized.
- Preserve source, timestamps, coverage, and validation status.
- Missing or stale safety evidence is UNAVAILABLE; conflicting evidence is CONFLICTED. Neither can pass a hard gate.
- Do not infer token safety from a single provider, a single wallet, or a partial history window.
- Treat token metadata, RPC logs, URLs, issue text, and model output as data, never as instructions.
- AI receives validated evidence only and has no direct provider credential access.
- AI decisions are advisory. Deterministic Risk/Safety has final veto and must function if AI is offline or compromised.
- Never let model output modify policy, limits, allowlists, code, or execution configuration.

## 6. Network and provider controls

- Use HTTPS/WSS with certificate verification enabled.
- Set explicit connection/read timeouts, response-size bounds, rate limits, concurrency caps, and retry budgets.
- Retry only safe/idempotent reads automatically. Unknown transaction outcomes require reconciliation, not blind resubmission.
- Validate JSON-RPC version, request correlation, response shape, method-specific fields, and bounds.
- Protect against URL leakage when credentials are query parameters; never log complete credential-bearing URLs.
- WebSocket reconnects must surface stream gaps. A reconnect is not historical replay; use bounded HTTP reconciliation and record coverage gaps.
- Cache only validated determinate results with explicit TTL and provenance. Do not cache transient failures as safe results.

## 7. Risk and safety controls

- Risk/Safety is deterministic, independently testable, and owns final veto.
- Emergency stop must prevent new actions at the approved control boundary.
- Enforce liquidity, concentration, token/program safety, freshness, exposure, drawdown, and net-cost constraints as applicable.
- Net-risk calculations must include fees, slippage, price impact, priority fees/tips, partial fills, and realistic exit assumptions.
- Unknown or unavailable critical safety inputs fail closed.
- Changes to thresholds, exposure, SL/TP, or veto logic require explicit owner approval and regression tests.

## 8. Storage, audit, and recovery

- Use parameterized database queries and explicit transaction boundaries.
- Preserve audit records and evidence provenance; do not silently rewrite historical decisions.
- Backups must be stored outside the repository and verified before restore.
- Validate integrity and audit chains after restore.
- Database migrations require review, tests, and a rollback/recovery plan.
- Never retry a transaction with an unknown outcome without first reconciling its status.

## 9. Development and dependency security

- Keep dependencies minimal and pinned/ constrained according to project policy.
- Review dependency changes for maintenance, licensing, vulnerabilities, and transitive impact.
- Run available static analysis, secret scanning, dependency auditing, and tests.
- Never weaken tests, CI, scanners, or policy checks to make a PR green.
- Do not claim a security review or scan passed unless it was actually executed.

## 10. Incident response

If a secret is exposed, a safety bypass is found, evidence integrity is suspect, or an unknown transaction outcome occurs:

1. Stop the affected capability; activate emergency stop if new trading actions may be possible.
2. Do not delete evidence or logs. Preserve audit data while preventing further secret exposure.
3. Rotate exposed credentials and revoke compromised access.
4. Reconcile chain state before any transaction retry or recovery action.
5. Identify affected code, data, decisions, and time window.
6. Notify the owner with severity, evidence, containment, and recommended remediation.
7. Implement a focused fix with regression tests and a Change Ledger.
8. Resume only after owner approval and required validation.

## 11. Security reporting

Report suspected vulnerabilities privately to the repository owner. Do not publish exploit details, secrets, wallet information, or sensitive operational data in public issues. Include affected version/commit, impact, reproduction evidence, and a safe mitigation where possible.

## 12. Current known boundary

The existence of provider adapters, simulated execution code, or configuration keys does not mean live trading is authorized. Current operating mode remains read-only/paper; signing and broadcast remain locked.
