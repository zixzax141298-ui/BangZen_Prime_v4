# Structure mapping: Master Blueprint 2026 to the current repository

**Status:** MANDATORY as the logical map for all new capability (see AI_RULES.yaml,
`master_blueprint_alignment.structure`). Physical placement stays in the existing layers until an
owner-approved migration PR. Verified against the repository on this date. Paths marked
`GAP` do not exist yet.

## Layer rule

Current physical layers: `bangzen_prime/domain`, `application`, `infrastructure`, `execution`,
`interfaces`, `bootstrap.py` (composition root), `settings.py`, `native/rust`. A blueprint folder
is implemented by a current layer. Do not create a second implementation of the same capability
in another layer (AI_RULES `repository_layout.placement_rules`).

## Blueprint section 15 mapping

| Blueprint target | Current location | Status | Action (blueprint section 16) |
|---|---|---|---|
| `main.py` | `bangzen_prime/__main__.py`, `interfaces/cli.py` | Present | KEEP |
| `core/orchestrator.py` | `application/supervisor.py`, `bootstrap.py` | Partial | KEEP; no new orchestrator |
| `core/event_bus.py` | `application/event_bus.py` | Present | KEEP |
| `core/config.py` | `settings.py` | Present | KEEP |
| `core/state.py` | `application/mode_controller.py` | Partial | FIX |
| `data/gateway.py` | `infrastructure/http.py`, `infrastructure/resilience/`, adapters | Partial, no single gateway | FIX or REPLACE with compatibility plan |
| `data/normalization.py` | `application/data_validation.py`, `adapters/market_data/parsing.py` | Partial | FIX |
| `data/quality.py` | `application/data_validation.py` | Partial | FIX |
| `data/provenance.py` | `infrastructure/persistence/sqlite/` (provenance in snapshots) | Partial | ADD |
| `data/cache.py` | `infrastructure/api_budget.py` (budget, not cache) | GAP | ADD |
| `providers/helius.py` | `infrastructure/adapters/chain/helius.py` | Present | KEEP |
| `providers/dexscreener.py` | `infrastructure/adapters/market_data/dexscreener.py` | Present | KEEP |
| `providers/birdeye.py` | none (name appears only in `intel.py`, `settings.py`) | GAP | ADD only after owner approves the provider |
| `providers/rugcheck.py` | `infrastructure/adapters/market_data/rugcheck.py` | Present | KEEP |
| `providers/jupiter.py` | `infrastructure/adapters/chain/jupiter.py` plus `jupiter_v2.py`, `jupiter_quote_v2.py`, `jupiter_price.py` | Duplicated | FIX: consolidate |
| `discovery/scanner.py` | `application/discovery.py`, `adapters/market_data/dexscreener_discovery.py` | Present | KEEP |
| `discovery/token_registry.py` | `domain/tokens.py`, `infrastructure/persistence/sqlite/repositories.py` | Present | KEEP |
| `discovery/deduplication.py` | `application/use_cases.py` (`_recent_scans`) | Partial | FIX: extract |
| `security/token_audit.py` | `application/use_cases.py` (`AuditTokenUseCase`) | Partial | KEEP |
| `security/holder_analysis.py` | `application/data_validation.py` (holder profile), adapters | Partial | FIX |
| `security/security_gate.py` | `filters/security.py`, `domain/token_2022_risk.py` | Present | KEEP |
| `market/market_analyzer.py` | `filters/market.py` | Partial | FIX |
| `market/liquidity.py`, `volume.py`, `transactions.py` | `filters/market.py`, `domain/quote_economics.py` | Partial | ADD where missing |
| `market/indicators.py` | `application/indicators.py` (tested); `domain/technical.py` (dormant, column bug, not used) | Present / dormant | KEEP `indicators.py`; FIX or remove `technical.py` |
| `strategies/base.py` | `application/strategies/base_strategy.py` (legacy `TradingStrategy`) | Legacy | REPLACE with compatibility plan |
| `strategies/rsi_volume.py` | `application/strategies/volume_surge.py` and similar; no RSI+Volume matching blueprint 9.1 | GAP | ADD |
| `strategies/cto.py` | none | GAP | ADD |
| `strategies/momentum.py` | `application/strategies/momentum.py` (legacy) | Legacy | REPLACE or FIX |
| `strategies/registry.py` | `application/strategies/__init__.py` (`STRATEGY_REGISTRY`) | Legacy | FIX |
| `scoring/opportunity.py` | `application/scoring.py` | Present | KEEP |
| `scoring/reason_codes.py` | `domain/signals.py` (`RejectReason`) | Present | KEEP |
| `risk/engine.py` | `application/risk_engine.py` | Present | KEEP (Risk Engine veto) |
| `risk/limits.py` | `RiskLimits` in `application/risk_engine.py` | Present | KEEP |
| `risk/position_sizing.py`, `slippage.py` | `domain/risk.py` (`size_position`) | Present | KEEP |
| `risk/emergency_stop.py` | `settings.py` (`EMERGENCY_STOP`) | Partial | ADD `HALT.flag` (AI_RULES `halt_flag`) |
| `execution/paper_engine.py` | `application/paper_trading.py` | Present | KEEP |
| `execution/fill_simulator.py`, `tp_sl.py` | `infrastructure/adapters/execution/simulated.py` | Present | KEEP |
| `execution/cost_model.py` | `domain/execution_economics.py`, `domain/quote_economics.py` | Present | KEEP |
| `notifications/telegram.py` | `infrastructure/adapters/messaging/telegram.py`, `adapters/notifications/telegram.py` | Duplicated | FIX: consolidate |
| `analytics/performance.py`, `trade_analysis.py`, `strategy_comparison.py`, `reports.py` | none (`scripts/paper_balance.py` only) | GAP | ADD (deterministic only) |
| `research/backtest.py` | `application/backtesting.py` | Present | KEEP |
| `research/walk_forward.py`, `out_of_sample.py`, `improvement_proposals.py` | none | GAP | ADD |
| `storage/database.py`, `repositories.py` | `infrastructure/persistence/sqlite/database.py`, `repositories.py` | Present (SQLite) | KEEP; PostgreSQL is a later migration |
| `storage/migrations/` | `infrastructure/migrations/*.sql` | Present | KEEP |
| `configs/providers.yaml`, `strategies.yaml`, `paper.yaml` | `config/*.json`, `.env.example` | Different format | FIX or ADD; do not duplicate |
| `tests/unit`, `integration` | present | Present | KEEP |
| `tests/security`, `regression`, `fixtures` | none (`tests/e2e` present) | GAP | ADD |
| `scripts/run_tests.py`, `run_paper.py` | `scripts/run_tests.py`; paper run through `interfaces/demo.py`, `soak.py` | Partial | ADD `run_paper.py` |
| `tools/ci.py` | present | Present | KEEP |
| `native/rust/` | present | Present | KEEP |
| `docs/ARCHITECTURE.md` | present | Present | KEEP |
| `docs/DATA_SCHEMA.md`, `RISK_POLICY.md`, `API_PROVIDERS.md`, `PAPER_TRADING.md` | none (related content in `docs/*`) | GAP | ADD |
| `docs/CHANGE_LEDGER.md` | several per-change ledgers in `docs/CHANGE_LEDGER_*.md` | Partial | ADD consolidated index |
| `reports/daily`, `reports/evaluation` | none | GAP | ADD |

## Environment variable mapping (blueprint section 4)

The blueprint uses logical names. Implemented names carry the `BANGZEN_` prefix. Settings reject
unknown `BANGZEN_*` keys, so do not add unprefixed variables.

| Blueprint name | Implemented name | Note |
|---|---|---|
| `HELIUS_API_KEY` | `BANGZEN_HELIUS_API_KEY` | Present |
| `DEXSCREENER_API_KEY` | none | Public endpoint, base URL `BANGZEN_DEXSCREENER_BASE_URL`. Do not invent a key. |
| `BIRDEYE_API_KEY` | `BANGZEN_BIRDEYE_API_KEY` | Setting exists, no adapter (GAP) |
| `RUGCHECK_API_KEY` | none | Public endpoint, base URL `BANGZEN_RUGCHECK_BASE_URL`. Use a key only if the endpoint requires one. |
| `JUPITER_API_KEY` | `BANGZEN_JUPITER_API_KEY` | Present, quote/paper only |
| `TELEGRAM_BOT_TOKEN` | `BANGZEN_TELEGRAM_BOT_TOKEN` | Present |
| `TELEGRAM_CHAT_ID` | `BANGZEN_TELEGRAM_ALLOWED_CHAT_IDS` | Implemented as an allowlist (comma-separated). A single chat ID is a subset. |

## Blueprint section 11.2 and 21: HALT.flag

Not implemented. Only `BANGZEN_EMERGENCY_STOP` exists. Required before the blueprint's emergency
stop rules are met. Owner approval is needed because it changes emergency-stop semantics
(AI_RULES `owner_approval_required_for`).
