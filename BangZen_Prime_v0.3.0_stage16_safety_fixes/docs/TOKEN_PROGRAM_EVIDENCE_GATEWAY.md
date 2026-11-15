# Token Program Evidence Gateway

## Purpose

PR #50 connects the existing read-only Helius Token-2022 mint reader to the real
Solana discovery scan and paper-entry risk path. The gateway first identifies the
mint account owner, then applies the deterministic Token-2022 extension policy.

## Flow

1. Solana candidate is discovered and a current market pair is selected.
2. TokenProgramEvidenceUseCase reads the exact mint account through the injected
   Helius getAccountInfo adapter at finalized commitment.
3. Only a classic SPL Token owner with a valid, initialized 82-byte Mint layout is
   classified as NOT_APPLICABLE to Token-2022 extension checks. Token accounts,
   uninitialized mints, and malformed classic layouts are rejected.
4. Token-2022 mints must have exact-mint, fresh, VERIFIED extension and
   configuration evidence, then pass evaluate_token_2022_risk.
5. BLOCKED results persist a rejected scan; HOLD results persist WATCH.
   Neither can reach scoring/AI/phase eligibility.
6. Paper entry re-reads the owner and extension evidence immediately before
   RiskEngine.evaluate, and passes the same evidence and program ID into the
   deterministic risk engine. Missing program evidence is a veto.

## Fail-closed behavior

- Missing Helius reader/API key, provider errors, malformed results, wrong mint,
  unknown program owner, stale/future evidence, partial configuration, and
  unsupported extensions cannot be treated as classic SPL Token.
- Classic SPL Token is NOT_APPLICABLE only after owner, initialized 82-byte Mint
  layout, and COption authority tags are validated.
- Token-2022 hard transfer-state flags produce BLOCKED.
- Transfer fees, permanent delegates, transfer hooks, and active authorities
  require review and remain WATCH/HOLD. They are not automatically labelled scams.
- RiskEngine requires matching mint evidence for both token programs; a caller-supplied
  program ID alone cannot bypass the final gate.

## API and performance boundary

The reader performs one bounded Helius getAccountInfo request per scan and a
fresh read before paper entry. It uses the existing Helius ResilientCaller,
timeout, retry and token-bucket configuration. No new provider, API key, polling
loop, database migration, or numeric risk threshold is introduced.

For production Solana scanning and paper entry, configure BANGZEN_HELIUS_API_KEY.
Without it, the gateway intentionally returns HOLD and Solana candidates remain
WATCH; it does not guess the token program.

## Safety boundary

- No wallet/private-key access, signing, transaction building, Jupiter execution,
  Jito submission, or broadcast is added.
- AI cannot override the gateway or RiskEngine.
- This is an eligibility/safety gate, not a profitability score or order approval.
- Existing RugCheck, holder, Sybil, AI, phase, portfolio and emergency-stop gates
  remain independent and continue to apply.

## Rollback

Revert PR #50. No persistent schema or configuration migration is required.
