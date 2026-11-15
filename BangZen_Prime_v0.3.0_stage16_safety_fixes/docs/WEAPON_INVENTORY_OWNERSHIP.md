# BANGZEN PRIME — Weapon Inventory & Ownership Map

## Audit result

The owner-provided list contains **29 entries** (8 Market Reading, 10 Risk Management, 6 Execution, 5 Core Strategy), not 28. The recursive `main` tree and targeted source inspection found 26 entries with a matching implementation path, one related-but-not-equivalent capability, and two entries not found. Some matching files are placeholders or thin wrappers; file existence is not proof of a complete weapon.

`config/weapon_catalog.json` is the machine-readable inventory. Status values deliberately distinguish implemented code from stubs, placeholders, partial capabilities, and missing modules.

## Ownership model

- **Data Gateway / provider adapters:** fetch external and on-chain observations, enforce timeouts/budgets/cache/provenance. They do not decide trades.
- **Evidence Engine:** normalize, timestamp, validate, deduplicate, and classify evidence as VERIFIED/PARTIAL/UNAVAILABLE/CONFLICTED. Missing data never becomes a clean result.
- **AI Manager:** may inspect validated evidence and request zero or one relevant analysis weapon on demand. It cannot manage funds, position sizing, BUY/SELL, TP/SL, slippage, TWAP, signing, submission, or broadcast.
- **Risk/Safety:** deterministic independent layer with final veto. Safety tools may feed evidence, but AI cannot override their fail-closed result.
- **Strategy / Execution:** core strategies and execution adapters remain under deterministic strategy, risk, and execution ownership; they are not AI Manager weapons.

## Findings requiring attention

- `dormant_whale_adapter`: no dedicated implementation found.
- `sibling_tracker_adapter`: no dedicated implementation found.
- `memo_hype_adapter`: `LunarCrushSentimentAdapter` exists, but it reports Solana ecosystem sentiment rather than token-specific hype; it is only a related capability.
- `second_life_strategy.py` currently contains a placeholder implementation returning `is_reviving=False`.
- `setup_engine.py` currently contains only a placeholder class.
- `smart_money_engine.py` is a thin wrapper; substantive wallet intelligence is in `smart_money_adapter.py`.
- `black_ops_engine.py` emits internal labels such as `BUY_DIP` and `EXIT`; these must never be passed to AI as authority to trade.
- `realistic_pumpfun.py` builds TP/SL trade-plan fields; keep outside AI Manager.

## Critical runtime gap

`AICommander` currently directly calls Sybil and Honeypot checks, then passes context to `AIBrain`; `AIBrain` still accepts BUY/SKIP. The current config allowlist alone does not enforce the intended AI boundary. A separate runtime integration PR must remove financial decision authority from AI, make weapon invocation on-demand and evidence-driven, and fail closed if the policy cannot be loaded or validated.

## Validation limits

This is a static inventory/ownership documentation change. It does not wire tools, alter thresholds, enable execution, or prove every module is active. Unit tests are added but NOT RUN; no CI-green or production-readiness claim is made.
