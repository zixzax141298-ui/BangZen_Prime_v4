# Change Ledger — PR #41: Jupiter V2 cost-aware quote

## Repository refs
- Base branch: `main`
- Base SHA: `122c74833aa339b58ce30bd0a780c2476238deed`
- Head branch: `feat/p3-jupiter-v2-cost-aware-quotes`
- Head SHA at implementation review checkpoint: `934bbdf23abe704b805a5515bda91b198716a44a`
- A ledger-only follow-up commit updates this file after that checkpoint.

## Intended changes
- Add a read-only Jupiter Swap API V2 `/order` quote adapter that omits `taker`.
- Validate mints, raw input/output amounts, router, order mode, fee basis points, fee mint,
  and optional platform-fee metadata.
- Preserve all monetary fee values in raw token units; do not silently convert or double-count.
- Add mocked unit tests and accounting/safety documentation.

## Explicit exclusions
- No transaction assembly, signing, wallet access, `/execute`, Jito submission, live trading,
  sizing, BUY/SELL decision, strategy threshold, or Risk/Safety policy change.
- No assumed gas, rent, priority-fee, slippage, price-impact, or tip values.

## Validation status
- Unit tests authored: `tests/unit/test_jupiter_quote_v2_adapter.py`; NOT RUN in authoring environment.
- `python3 tools/ci.py`: BLOCKED / NOT RUN; file not found in inspected `main`.
- GitHub Actions: no workflow runs or commit status checks were returned for the reviewed PR head
  when checked. CI status is therefore NOT RUN / UNAVAILABLE, not PASS.
- No claim of CI green, test pass, or production readiness.

## Known limitations
- This adapter captures fee rates and raw fee amounts only. Token-decimal normalization and
  conversion from fee mint to the configured quote currency remain a separate integration task.
- Quote data is a snapshot, not an execution or fill guarantee.


## Contract correction
- Corrected the parser to take the fee token from top-level `feeMint`; the official V2
  response nests only `amount` and `feeBps` under `platformFee`.
- Updated the mock fixture to match the documented response shape.
- Correction commit: `3ba33a63fc213dcb4a2cce7b776f990af441d7f7`.
