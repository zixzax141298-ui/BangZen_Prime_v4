# Strategy research and historical validation

## Current status

- Strategy score is a heuristic ranking score, not a probability or expected return.
- The current `ScoreBreakdown.confidence` is only `score / 100`; it is not statistically
  calibrated and must not be described as a win probability.
- Current fixed liquidity/volume score caps and RSI-centred momentum are provisional.
- Repository tests use fixtures; no verified, point-in-time historical Solana dataset
  is included. No thresholds or weights are claimed to be optimal.

## Evaluation protocol

1. Acquire timestamped OHLCV data from a documented source and retain raw snapshots,
   source identifiers, pair/mint identity, timezone, interval, and retrieval time.
2. Include dead, rugged, delisted, and illiquid pairs; avoid survivorship bias.
3. Split chronologically into development, validation, and untouched test periods.
4. Generate each candidate using only data available at its signal timestamp.
5. Replay entry no earlier than the next candle open. Include fees and adverse slippage
   on both sides; use conservative stop-first handling when OHLC cannot establish order.
6. Report sample size, net expectancy, win rate, profit factor, max drawdown, exposure,
   holding time, and results by lifecycle phase and market regime.
7. Run walk-forward tests and compare against buy-and-hold and no-trade baselines.
8. Reject parameter changes that only improve in-sample results or depend on missing data.
9. Paper-test the frozen candidate configuration before any live authorization.

## Backtest module scope

`bangzen_prime.application.backtesting.evaluate_candidates` evaluates supplied
`TradeCandidate` plans against `HistoricalCandle` sequences. It does not discover
signals, call external APIs, access wallet keys, or execute transactions. It is a
research-only component and must remain isolated from live execution.

## Required data before strategy retuning

A representative, point-in-time OHLCV corpus for Solana pairs; token/pair lifecycle
metadata; liquidity and volume snapshots; safety/holder observations with timestamps;
and realistic route-specific fee, slippage, priority-fee, and failed-transaction data.
Missing evidence must be labelled unavailable, not imputed as safe or profitable.
