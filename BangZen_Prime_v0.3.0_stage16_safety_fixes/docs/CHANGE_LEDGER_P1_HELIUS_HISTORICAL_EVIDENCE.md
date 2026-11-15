# Change Ledger — P1 Helius Historical Evidence

## Scope
- Add a read-only Helius HTTP history reader for `getSignaturesForAddress` and `getTransaction`.
- Validate address/signature formats, slots, block times, fees, account keys, and balance arrays.
- Represent missing transaction metadata explicitly as unavailable.
- Add durable SQLite signature storage with idempotent inserts and an atomic pagination checkpoint.
- Track pagination coverage as `MORE_AVAILABLE`, `EXHAUSTED`, or `FAILED`; a full page is never marked exhausted.

## Evidence semantics
- Provider responses are observations, not proof of token safety or full chain coverage.
- `EXHAUSTED` means the provider returned fewer entries than requested for that pagination request; it does not prove archival completeness, a time-bounded history, or coverage across every account involved.
- AI must not treat `MORE_AVAILABLE`, `FAILED`, missing transaction metadata, or cross-source contradictions as safe evidence.
- The store records signature metadata only; no raw secrets, private keys, or signed transactions.

## Safety
- No AI decisions, weapon selection, risk thresholds, signing, transaction construction, or broadcast behavior are changed.
- Live execution remains locked.
- No API key is committed or included in exception messages.

## Validation
- Tests added for page validation, malformed provider data, transaction metadata, pagination status, idempotency, and checkpoints.
- Tests have not been executed in this environment. No CI/test-pass claim is made.
