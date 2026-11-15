# Change Ledger — P0 Fail-Closed Honeypot Adapter

## Scope
- Make the honeypot result explicitly distinguish a completed provider check from an unavailable result.
- Only an explicit boolean `False` from a completed dynamic-tax check is represented as safe.
- Provider exceptions, malformed responses, and cache-window skips return `available=False` and `is_honeypot=None`.
- Failed and malformed checks are not cached, allowing a later retry.
- Add an explicit `is_safe` property that is true only for an available, explicit safe result.
- Validate the mint and cache interval before calling the provider.

## Safety rationale
A failed or skipped check is not evidence that a token can be sold. Treating provider errors as safe can allow an unverified token to proceed through downstream screening. This change makes uncertainty explicit and prevents the adapter itself from manufacturing a clean verdict.

## Compatibility and integration
- `HoneypotReport.is_honeypot` is now nullable and `available` is explicit. Downstream consumers must check availability before interpreting the boolean.
- Repository search found no current call sites for `check_honeypot` / `HoneypotReport`; this PR hardens the adapter contract but does not claim that the main scan pipeline now invokes it.
- This PR does not add live execution, signing, or broadcasting.

## Tests
- Added unit tests for explicit safe, honeypot, provider exception, retry after failure, cache skip, forced refresh, malformed provider value, and invalid cache interval.
- Tests have NOT been executed in this change session.
- CI result is pending after PR creation; no green status is claimed.
