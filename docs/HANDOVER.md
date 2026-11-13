# Handover

Entry point: `bangzen_prime/interfaces/cli.py`. Composition root: `bangzen_prime/bootstrap.py`.
Architecture: `docs/ARCHITECTURE.md`. Release notes: `docs/RELEASE_NOTES.md`.

State: Stages 1 to 11 are implemented as described in `docs/STAGES.md`, with every test in the
suite passing offline. Live trading and transaction broadcast are locked. Nothing has been
exercised against real networks or chains.

Owner decisions still needed before any live-adjacent work:
1. Approve or reject the Stage 9 scope beyond mock validation. Real signing needs a separate
   security review. The brief requires it.
2. Choose the quote provider and RPC endpoint for devnet, if devnet work is approved.
3. Confirm the RugCheck schema and score direction against the official documentation.
4. Decide whether SQLite should move to `aiosqlite`, and whether the application/infrastructure
   boundary should be tightened (see KNOWN_LIMITATIONS).

Verification to run where network access exists:
- ruff, mypy, pytest with coverage.py (branch coverage), `python -m build`.
- The CI workflow on a hosted runner.
- The opt-in real-API smoke test. It does not exist yet and must stay separate from CI.
