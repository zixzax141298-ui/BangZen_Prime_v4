# Change ledger: Stage 10, e2e paper tests get the production price and spread sources (owner-approved)

Owner approval in chat on 2026-11-15 for the fixture change.

## Cause
The e2e helpers built `PaperTradingUseCase` without `price_lookup` or `spread_lookup`. The engine then rejected
every signal (`MARKET_PRICE_UNAVAILABLE`, then `SPREAD_UNAVAILABLE`). No accepted signal existed, so setup
queries returned None (2 ERROR), and assertions on approval failed (5 FAIL).

## Change (tests only, no production code changed)
- `tests/e2e/test_paper_flow.py` and `tests/e2e/test_v3_flow.py`: pass
  `price_lookup=latest_sampled_price(db)` and `spread_lookup=lambda _mint: SIMULATED_SPREAD_PCT`.
  Both come from `core/interfaces/demo.py`, the same sources the offline demo uses.
  The price is the latest stored price sample for the mint. Nothing is hard-coded.

## Result
- The 15 e2e paper and v3 tests pass.
- Full suite: 878 tests, OK. Earlier failures were 5 FAIL and 2 ERROR. Those were caused by this fixture,
  not by the production code.

## Caveat
The spread is a synthetic assumption (`SIMULATED_SPREAD_PCT = 0.2`, see its comment in demo.py). It is not observed data.
These tests check the paper flow logic. They do not prove market behaviour.
