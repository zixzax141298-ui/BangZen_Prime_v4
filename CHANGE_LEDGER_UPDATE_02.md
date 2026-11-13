# Change Ledger — Update 02

## Added
- `bangzen_prime/application/backtesting.py`
  - Replay candidate plan only from the candle after the signal candle closes.
  - Per-side fee and adverse slippage applied to entry and exit.
  - Conservative stop-first handling when a candle touches both SL and TP.
  - Stop-gap handling uses the worse candle open.
  - Reports net PnL/return, expectancy, win rate, profit factor when defined,
    peak-to-trough drawdown, win/loss/breakeven counts, and rejected candidates.
  - Validates OHLC, finite Decimal inputs, timezone-aware strictly increasing timestamps,
    candidate identity, and configuration.
- `tests/unit/test_backtesting.py`: 11 focused tests.
- `docs/STRATEGY_RESEARCH.md`: historical data and walk-forward validation protocol.

## Updated
- `docs/KNOWN_LIMITATIONS.md`: describes evaluator scope and research constraints.
- `MANIFEST.sha256`: includes new source/test/docs files.

## Explicitly unchanged
- Strategy weights, RSI periods, score thresholds, stop/target multipliers.
- Wallet signing, transaction builder, Jupiter/RPC broadcast, and live execution locks.
- API key configuration and API call behavior.
- Telegram signal-only mode and dashboard.

## Validation performed on supplied ZIP source
- `python scripts/run_tests.py`: 517 passed, 0 failed, 0 errors, 0 skipped.
- `python -m compileall -q bangzen_prime tests scripts`: passed.
- `python scripts/check_unused_imports.py`: passed.
- Wheel build and clean-venv CLI smoke test: passed.

Black, Ruff, and Mypy were not installed in the local environment. Hosted GitHub Actions
was not run from this package, so GitHub CI status is unverified. No claim of 100% hosted
CI is made. No real-market historical corpus was included; no profitability claim or
parameter retuning was made.
