# Release notes: Bangzen Prime 0.2.0

Added in 0.2.0 (on top of 0.1.0):
- Read-only market intel: Birdeye token overview, Solana Tracker holders.
- Jupiter quote adapter (quote only, 20-second local expiry).
- Jito read-only adapter: tip accounts and tip floor. Dynamic tip policy capped by share of
  expected gain and an absolute cap. Bundle plans are built locally and never submitted.
- Helius RPC adapter (balances and signature status). Simulate and send are refused.
- Yellowstone gRPC ingestion interface with a mock stream. The live client refuses to start
  until protobuf stubs are generated.
- AI brain with providers anthropic, openai, and grok, switched by BANGZEN_AI_PROVIDER. Output is
  strictly parsed. Anything invalid or unavailable becomes SKIP. Disabled by default.
- Heartbeats and watchdog. A worker silent for more than 5 seconds triggers the emergency latch.
  Paper trading halts until an operator resets it, and each trigger or reset is audited.
- Reconciliation worker: compares on-chain token balance with the database and triggers the
  emergency latch on mismatch beyond tolerance.
- Rust bridge (optional native module with automatic Python fallback). Telegram escaping uses it.

Locked in this release, enforced in configuration and code:
- LIVE_TRADING=false is required. BROADCAST_ENABLED=false is required.
- No signing key is read or stored. No sendBundle, sendTransaction, or swap execution exists.

Not verified in this build:
- The Rust crate was not compiled (no toolchain). The Python fallback is the tested path.
- Real API calls: none were made. Field names beyond the documented examples are unverified.
