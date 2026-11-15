# Change Ledger — Restore Audit Token Use Case

## Scope
- Restore the `AuditTokenUseCase` imported by the composition root.
- Execute the synchronous safety adapter in a worker thread so network I/O does not block the async scan loop.
- Validate that the returned `SafetyAssessment` is well-formed and bound to the exact requested chain and mint.

## Safety behavior
- Provider exceptions propagate to the existing scan safety boundary, which records `SAFETY_UNAVAILABLE` / WATCH.
- Invalid assessment types or identity mismatches raise `DomainError`; they are never treated as a clean safety result.
- No execution, signing, or broadcast behavior is added.

## Tests
- Added unit coverage for valid identity, mint mismatch, malformed provider result, and provider exception propagation.
- Tests were not executed in this environment. GitHub Actions is currently blocked before job startup by account billing/spending limits; no CI pass is claimed.

## Follow-up
- Integrate the fail-closed Honeypot and Sybil evidence into the scan safety pipeline as a separate change after reviewing holder-data contracts.
