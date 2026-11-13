# Security

- Live trading is locked in `Settings.__post_init__`, and again in the simulated execution
  constructor (`paper` and `dry_run` must be true).
- Transaction broadcast is locked in `Settings` (`broadcast_enabled` must be false). The chain
  use case refuses BROADCAST unless `broadcast_allowed` is passed explicitly, and bootstrap
  never passes it. The only production signer, `DisabledSigner`, refuses every call.
- No signing key, wallet, seed phrase, or RPC endpoint is read, stored, or used by this code.
- Chain plans are inspected before simulation: unknown programs, foreign sources, unknown
  destinations, a fee payer that is not the owner, and a transfer total that differs from the
  quote are all rejected.
- Secrets: the Telegram token is excluded from `repr`. Logs pass through a redaction filter
  (Telegram token pattern and key=value secrets). HTTP error messages do not include URLs.
- Telegram: only allowlisted chat ids receive messages or command replies. Output is
  HTML-escaped. The only command is read-only `/status`.
- Audit: risk decisions and accepted signals are written to a SHA-256 hash chain.
  `audit-verify`, `health`, and `restore` detect edits and deletions.
- Backups are verified before restore (integrity check, required tables, audit chain). A failed
  verification leaves the live database untouched.
- Network: tests run with a socket guard (`tests/__init__.py`) that raises on any real
  connection attempt. HTTP in tests uses in-memory fakes.
- Not audited. Dependency supply chain is minimal (no third-party runtime dependencies).
