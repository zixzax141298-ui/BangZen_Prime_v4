# Change Ledger — P2 Net Execution Economics

- Repository: ripsterxiui98-coder/BangZenPrime-v3
- Base branch: main
- Base SHA: 38812c761a9e77c63a9ef07c3a91de86e5dafb4c
- Objective: introduce a pure quote-currency round-trip cost calculator.
- Added:
  - bangzen_prime/domain/execution_economics.py
  - tests/unit/test_execution_economics.py
  - docs/NET_EXECUTION_ECONOMICS.md
  - docs/CHANGE_LEDGER_P2_NET_EXECUTION_ECONOMICS.md
- Costs: entry/exit fees, entry/exit slippage, entry/exit price impact, priority fee,
  Jito tip, rent reserve, failed-exit reserve, and other costs.
- Formula: net PnL = gross exit - entry notional - all explicit costs.
- No provider I/O, quote retrieval, transaction building, wallet, signing, broadcast,
  strategy threshold, sizing, or risk policy changes.
- Unit tests added but NOT RUN in authoring environment.
- python3 tools/ci.py: BLOCKED / NOT RUN; absent from inspected main tree.
- GitHub Actions: pending at PR creation; no pass claim.
- Known limitation: callers must normalize all values into one quote currency and avoid
  double-counting costs already reflected in gross exit estimate.
- Rollback: revert the additive PR; no database or external-state migration.
