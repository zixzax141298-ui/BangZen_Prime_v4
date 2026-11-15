# Structure migration: current layout to blueprint section 15

**Status: applied in the repo tree (stage 5, see CHANGE_LEDGER_STAGE5_STRUCTURE_MIGRATION.md). Full suite run: 913 tests, same pre-existing failure set as before the migration.**

## What changed
- Modules moved to blueprint folders (`core/`, `data/`, `discovery/`, `security/`, `market/`,
  `strategies/`, `scoring/`, `risk/`, `execution/`, `notifications/`, `analytics/`, `research/`,
  `storage/`). The `domain/`, `application/`, `infrastructure/`, `filters/`, `native/` layers no
  longer exist.
- `config/` renamed to `configs/` (files are still JSON; the blueprint names YAML).
- Blueprint folders created empty where no code exists yet: `tests/security`, `tests/regression`,
  `tests/fixtures`, `reports/daily`, `reports/evaluation`.
- Import paths, string references (`mock.patch`, `importlib`), and `pyproject.toml` package-data
  updated. Negative tests for removed modules now point at the new locations.

## Known issues (to resolve before merge)
- Governance files still describe the old layers: `AI_RULES.yaml` (`repository_layout`,
  `master_blueprint_alignment`), `AGENTS.md`, `SECURITY.md`, `RULES.md`, and
  `docs/STRUCTURE_MAPPING_2026.md`. Changing them needs owner approval.
- Duplicate implementations kept as separate files (placement rule violation until consolidated):
  Jupiter (`jupiter.py`, `jupiter_v2.py`, `jupiter_quote_v2.py`), Telegram
  (`notifications/telegram.py`, `notifications/messaging_telegram.py`).
- `grpc_stream` loads `yellowstone_pb2`, a generated stub that is not in the repository.
- `filters/__init__.py`, `application/__init__.py`, `domain/__init__.py`, `infrastructure/**/__init__.py`,
  and `adapters/**/__init__.py` were dropped. Their content was not used by any import.
- `market/market_analyzer.py` still imports `discovery.models` and `discovery.providers.dexscreener`,
  which did not exist in the original either.
- The logger name `bangzen_prime.native` is kept, so log filters do not change.
- Strategy files and `core/` modules were placed by judgment where the blueprint has no slot;
  review placement before merge.

## Module mapping (old to new)

| Old | New |
|---|---|
| `bangzen_prime/__main__.py` | `bangzen_prime/__main__.py` |
| `bangzen_prime/application/autopsy_engine.py` | `bangzen_prime/analytics/autopsy_engine.py` |
| `bangzen_prime/bootstrap.py` | `bangzen_prime/core/bootstrap.py` |
| `bangzen_prime/settings.py` | `bangzen_prime/core/config.py` |
| `bangzen_prime/errors.py` | `bangzen_prime/core/errors.py` |
| `bangzen_prime/application/event_bus.py` | `bangzen_prime/core/event_bus.py` |
| `bangzen_prime/application/heartbeat.py` | `bangzen_prime/core/heartbeat.py` |
| `bangzen_prime/logging_utils.py` | `bangzen_prime/core/logging_utils.py` |
| `bangzen_prime/application/monitor.py` | `bangzen_prime/core/monitor.py` |
| `bangzen_prime/infrastructure/observability/health.py` | `bangzen_prime/core/observability/health.py` |
| `bangzen_prime/infrastructure/observability/metrics.py` | `bangzen_prime/core/observability/metrics.py` |
| `bangzen_prime/config.py` | `bangzen_prime/core/operating_config.py` |
| `bangzen_prime/domain/operating_mode.py` | `bangzen_prime/core/operating_mode.py` |
| `bangzen_prime/application/outbox_worker.py` | `bangzen_prime/core/outbox_worker.py` |
| `bangzen_prime/application/phase_policy.py` | `bangzen_prime/core/phase_policy.py` |
| `bangzen_prime/application/ports.py` | `bangzen_prime/core/ports.py` |
| `bangzen_prime/native/rust_bridge.py` | `bangzen_prime/core/rust_bridge.py` |
| `bangzen_prime/domain/session_manager.py` | `bangzen_prime/core/session_manager.py` |
| `bangzen_prime/domain/shared.py` | `bangzen_prime/core/shared.py` |
| `bangzen_prime/application/mode_controller.py` | `bangzen_prime/core/state.py` |
| `bangzen_prime/application/supervisor.py` | `bangzen_prime/core/supervisor.py` |
| `bangzen_prime/application/use_cases.py` | `bangzen_prime/core/use_cases.py` |
| `bangzen_prime/domain/values.py` | `bangzen_prime/core/values.py` |
| `bangzen_prime/infrastructure/api_budget.py` | `bangzen_prime/data/api_budget.py` |
| `bangzen_prime/application/api_budget_defaults.py` | `bangzen_prime/data/api_budget_defaults.py` |
| `bangzen_prime/application/data_validation.py` | `bangzen_prime/data/data_validation.py` |
| `bangzen_prime/infrastructure/http.py` | `bangzen_prime/data/http.py` |
| `bangzen_prime/domain/mint_metadata.py` | `bangzen_prime/data/mint_metadata.py` |
| `bangzen_prime/infrastructure/adapters/market_data/parsing.py` | `bangzen_prime/data/parsing.py` |
| `bangzen_prime/infrastructure/adapters/market_data/dexscreener.py` | `bangzen_prime/data/providers/dexscreener.py` |
| `bangzen_prime/infrastructure/chain/grpc_stream.py` | `bangzen_prime/data/providers/grpc_stream.py` |
| `bangzen_prime/infrastructure/adapters/chain/helius.py` | `bangzen_prime/data/providers/helius.py` |
| `bangzen_prime/infrastructure/adapters/chain/helius_history.py` | `bangzen_prime/data/providers/helius_history.py` |
| `bangzen_prime/infrastructure/adapters/chain/helius_mint_metadata.py` | `bangzen_prime/data/providers/helius_mint_metadata.py` |
| `bangzen_prime/infrastructure/chain/helius_websocket.py` | `bangzen_prime/data/providers/helius_websocket.py` |
| `bangzen_prime/infrastructure/adapters/market_data/intel.py` | `bangzen_prime/data/providers/intel.py` |
| `bangzen_prime/infrastructure/adapters/chain/jupiter.py` | `bangzen_prime/data/providers/jupiter.py` |
| `bangzen_prime/infrastructure/adapters/market_data/jupiter_price.py` | `bangzen_prime/data/providers/jupiter_price.py` |
| `bangzen_prime/infrastructure/adapters/chain/jupiter_quote_normalizer.py` | `bangzen_prime/data/providers/jupiter_quote_normalizer.py` |
| `bangzen_prime/infrastructure/adapters/chain/jupiter_quote_v2.py` | `bangzen_prime/data/providers/jupiter_quote_v2.py` |
| `bangzen_prime/infrastructure/adapters/chain/jupiter_v2.py` | `bangzen_prime/data/providers/jupiter_v2.py` |
| `bangzen_prime/infrastructure/adapters/market_data/lunarcrush.py` | `bangzen_prime/data/providers/lunarcrush.py` |
| `bangzen_prime/infrastructure/adapters/market_data/news_adapter.py` | `bangzen_prime/data/providers/news_adapter.py` |
| `bangzen_prime/infrastructure/adapters/market_data/rugcheck.py` | `bangzen_prime/data/providers/rugcheck.py` |
| `bangzen_prime/infrastructure/adapters/onchain/solana_ws_adapter.py` | `bangzen_prime/data/providers/solana_ws_adapter.py` |
| `bangzen_prime/application/resilience.py` | `bangzen_prime/data/resilience.py` |
| `bangzen_prime/infrastructure/resilience/async_retry.py` | `bangzen_prime/data/retry/async_retry.py` |
| `bangzen_prime/infrastructure/resilience/policies.py` | `bangzen_prime/data/retry/policies.py` |
| `bangzen_prime/infrastructure/adapters/market_data/cross_chain_radar_adapter.py` | `bangzen_prime/discovery/cross_chain_radar_adapter.py` |
| `bangzen_prime/infrastructure/adapters/market_data/dexscreener_discovery.py` | `bangzen_prime/discovery/dexscreener_discovery.py` |
| `bangzen_prime/domain/lifecycle.py` | `bangzen_prime/discovery/lifecycle.py` |
| `bangzen_prime/infrastructure/adapters/market_data/lp_sniper_adapter.py` | `bangzen_prime/discovery/lp_sniper_adapter.py` |
| `bangzen_prime/application/discovery.py` | `bangzen_prime/discovery/scanner.py` |
| `bangzen_prime/domain/tokens.py` | `bangzen_prime/discovery/tokens.py` |
| `bangzen_prime/infrastructure/adapters/execution/base58.py` | `bangzen_prime/execution/base58.py` |
| `bangzen_prime/application/controlled_execution.py` | `bangzen_prime/execution/controlled_execution.py` |
| `bangzen_prime/domain/execution.py` | `bangzen_prime/execution/execution.py` |
| `bangzen_prime/domain/execution_economics.py` | `bangzen_prime/execution/execution_economics.py` |
| `bangzen_prime/application/execution_use_case.py` | `bangzen_prime/execution/execution_use_case.py` |
| `bangzen_prime/infrastructure/adapters/chain/jito.py` | `bangzen_prime/execution/jito.py` |
| `bangzen_prime/infrastructure/adapters/chain/jito_adapter.py` | `bangzen_prime/execution/jito_adapter.py` |
| `bangzen_prime/infrastructure/adapters/chain/jito_bundle.py` | `bangzen_prime/execution/jito_bundle.py` |
| `bangzen_prime/application/lifecycle.py` | `bangzen_prime/execution/lifecycle.py` |
| `bangzen_prime/application/lifecycle_weapon_router.py` | `bangzen_prime/execution/lifecycle_weapon_router.py` |
| `bangzen_prime/domain/orders.py` | `bangzen_prime/execution/orders.py` |
| `bangzen_prime/application/paper_trading.py` | `bangzen_prime/execution/paper_trading.py` |
| `bangzen_prime/domain/quote_economics.py` | `bangzen_prime/execution/quote_economics.py` |
| `bangzen_prime/application/realistic_pumpfun.py` | `bangzen_prime/execution/realistic_pumpfun.py` |
| `bangzen_prime/application/reconciliation.py` | `bangzen_prime/execution/reconciliation.py` |
| `bangzen_prime/application/secure_execution_gateway.py` | `bangzen_prime/execution/secure_execution_gateway.py` |
| `bangzen_prime/infrastructure/adapters/execution/signing.py` | `bangzen_prime/execution/signing.py` |
| `bangzen_prime/infrastructure/adapters/execution/simulated.py` | `bangzen_prime/execution/simulated.py` |
| `bangzen_prime/domain/tip.py` | `bangzen_prime/execution/tip.py` |
| `bangzen_prime/execution/twap_execution.py` | `bangzen_prime/execution/twap_execution.py` |
| `bangzen_prime/application/wallet_access.py` | `bangzen_prime/execution/wallet_access.py` |
| `bangzen_prime/infrastructure/adapters/execution/wallet_signer.py` | `bangzen_prime/execution/wallet_signer.py` |
| `bangzen_prime/application/indicators.py` | `bangzen_prime/market/indicators.py` |
| `bangzen_prime/filters/market.py` | `bangzen_prime/market/market_analyzer.py` |
| `bangzen_prime/domain/technical.py` | `bangzen_prime/market/technical.py` |
| `bangzen_prime/infrastructure/adapters/messaging/telegram.py` | `bangzen_prime/notifications/messaging_telegram.py` |
| `bangzen_prime/application/notifications.py` | `bangzen_prime/notifications/notifications.py` |
| `bangzen_prime/infrastructure/adapters/notifications/telegram.py` | `bangzen_prime/notifications/telegram.py` |
| `bangzen_prime/application/ai_brain.py` | `bangzen_prime/research/ai_brain.py` |
| `bangzen_prime/application/ai_commander.py` | `bangzen_prime/research/ai_commander.py` |
| `bangzen_prime/application/ai_manager_contract.py` | `bangzen_prime/research/ai_manager_contract.py` |
| `bangzen_prime/infrastructure/ai/providers.py` | `bangzen_prime/research/ai_providers.py` |
| `bangzen_prime/application/backtesting.py` | `bangzen_prime/research/backtesting.py` |
| `bangzen_prime/risk/anti_sl_hunt.py` | `bangzen_prime/risk/anti_sl_hunt.py` |
| `bangzen_prime/risk/dynamic_slippage.py` | `bangzen_prime/risk/dynamic_slippage.py` |
| `bangzen_prime/domain/risk.py` | `bangzen_prime/risk/risk.py` |
| `bangzen_prime/application/risk_engine.py` | `bangzen_prime/risk/risk_engine.py` |
| `bangzen_prime/application/risk_state.py` | `bangzen_prime/risk/risk_state.py` |
| `bangzen_prime/application/ev_engine.py` | `bangzen_prime/scoring/ev_engine.py` |
| `bangzen_prime/domain/ev_model.py` | `bangzen_prime/scoring/ev_model.py` |
| `bangzen_prime/domain/metadata_scorer.py` | `bangzen_prime/scoring/metadata_scorer.py` |
| `bangzen_prime/application/scoring.py` | `bangzen_prime/scoring/scoring.py` |
| `bangzen_prime/domain/signals.py` | `bangzen_prime/scoring/signals.py` |
| `bangzen_prime/application/auto_blacklist_manager.py` | `bangzen_prime/security/auto_blacklist_manager.py` |
| `bangzen_prime/application/black_ops_engine.py` | `bangzen_prime/security/black_ops_engine.py` |
| `bangzen_prime/domain/copycat_trap.py` | `bangzen_prime/security/copycat_trap.py` |
| `bangzen_prime/infrastructure/adapters/onchain/dev_predictor_adapter.py` | `bangzen_prime/security/dev_predictor_adapter.py` |
| `bangzen_prime/infrastructure/adapters/chain/helius_token_2022_extensions.py` | `bangzen_prime/security/helius_token_2022_extensions.py` |
| `bangzen_prime/infrastructure/adapters/onchain/honeypot_adapter.py` | `bangzen_prime/security/honeypot_adapter.py` |
| `bangzen_prime/infrastructure/adapters/onchain/kol_exit_adapter.py` | `bangzen_prime/security/kol_exit_adapter.py` |
| `bangzen_prime/domain/pre_dump_radar.py` | `bangzen_prime/security/pre_dump_radar.py` |
| `bangzen_prime/filters/security.py` | `bangzen_prime/security/security_gate.py` |
| `bangzen_prime/domain/sequential_bundle_detector.py` | `bangzen_prime/security/sequential_bundle_detector.py` |
| `bangzen_prime/infrastructure/adapters/onchain/smart_money_adapter.py` | `bangzen_prime/security/smart_money_adapter.py` |
| `bangzen_prime/infrastructure/adapters/onchain/sniper_ban_adapter.py` | `bangzen_prime/security/sniper_ban_adapter.py` |
| `bangzen_prime/infrastructure/adapters/onchain/sybil_adapter.py` | `bangzen_prime/security/sybil_adapter.py` |
| `bangzen_prime/domain/token_2022_extension_config.py` | `bangzen_prime/security/token_2022_extension_config.py` |
| `bangzen_prime/domain/token_2022_extension_evidence.py` | `bangzen_prime/security/token_2022_extension_evidence.py` |
| `bangzen_prime/domain/token_2022_extensions.py` | `bangzen_prime/security/token_2022_extensions.py` |
| `bangzen_prime/domain/token_2022_risk.py` | `bangzen_prime/security/token_2022_risk.py` |
| `bangzen_prime/application/token_program_evidence.py` | `bangzen_prime/security/token_program_evidence.py` |
| `bangzen_prime/domain/token_programs.py` | `bangzen_prime/security/token_programs.py` |
| `bangzen_prime/infrastructure/persistence/sqlite/attempts.py` | `bangzen_prime/storage/attempts.py` |
| `bangzen_prime/infrastructure/persistence/sqlite/chain_history.py` | `bangzen_prime/storage/chain_history.py` |
| `bangzen_prime/infrastructure/persistence/sqlite/database.py` | `bangzen_prime/storage/database.py` |
| `bangzen_prime/infrastructure/persistence/sqlite/lifecycle.py` | `bangzen_prime/storage/lifecycle.py` |
| `bangzen_prime/infrastructure/persistence/sqlite/maintenance.py` | `bangzen_prime/storage/maintenance.py` |
| `bangzen_prime/infrastructure/persistence/sqlite/outbox.py` | `bangzen_prime/storage/outbox.py` |
| `bangzen_prime/infrastructure/persistence/sqlite/repositories.py` | `bangzen_prime/storage/repositories.py` |
| `bangzen_prime/application/strategies/base_strategy.py` | `bangzen_prime/strategies/base_strategy.py` |
| `bangzen_prime/application/strategies/degen_ignition.py` | `bangzen_prime/strategies/degen_ignition.py` |
| `bangzen_prime/application/strategies/flush_recovery.py` | `bangzen_prime/strategies/flush_recovery.py` |
| `bangzen_prime/application/strategies/graduation.py` | `bangzen_prime/strategies/graduation.py` |
| `bangzen_prime/application/strategies/mean_reversion.py` | `bangzen_prime/strategies/mean_reversion.py` |
| `bangzen_prime/application/strategies/migration_snipe.py` | `bangzen_prime/strategies/migration_snipe.py` |
| `bangzen_prime/application/strategies/momentum.py` | `bangzen_prime/strategies/momentum.py` |
| `bangzen_prime/application/strategies/narrative.py` | `bangzen_prime/strategies/narrative.py` |
| `bangzen_prime/application/strategies/range_rotation.py` | `bangzen_prime/strategies/range_rotation.py` |
| `bangzen_prime/application/strategies/reversal.py` | `bangzen_prime/strategies/reversal.py` |
| `bangzen_prime/application/second_life_strategy.py` | `bangzen_prime/strategies/second_life_strategy.py` |
| `bangzen_prime/application/setup_engine.py` | `bangzen_prime/strategies/setup_engine.py` |
| `bangzen_prime/application/smart_money_engine.py` | `bangzen_prime/strategies/smart_money_engine.py` |
| `bangzen_prime/application/strategies/sniper.py` | `bangzen_prime/strategies/sniper.py` |
| `bangzen_prime/application/strategy_dispatcher.py` | `bangzen_prime/strategies/strategy_dispatcher.py` |
| `bangzen_prime/application/strategies/volatility_breakout.py` | `bangzen_prime/strategies/volatility_breakout.py` |
| `bangzen_prime/application/strategies/volume_anomaly.py` | `bangzen_prime/strategies/volume_anomaly.py` |
| `bangzen_prime/application/strategies/volume_surge.py` | `bangzen_prime/strategies/volume_surge.py` |
| `bangzen_prime/infrastructure/migrations/0001_init.sql` | `bangzen_prime/storage/migrations/0001_init.sql` |
| `bangzen_prime/infrastructure/migrations/0002_execution.sql` | `bangzen_prime/storage/migrations/0002_execution.sql` |
| `bangzen_prime/infrastructure/migrations/0003_controlled_execution.sql` | `bangzen_prime/storage/migrations/0003_controlled_execution.sql` |
| `bangzen_prime/infrastructure/migrations/0004_token_lifecycle.sql` | `bangzen_prime/storage/migrations/0004_token_lifecycle.sql` |
| `bangzen_prime/infrastructure/migrations/0005_chain_history.sql` | `bangzen_prime/storage/migrations/0005_chain_history.sql` |
| `bangzen_prime/interfaces/banner.py` | `bangzen_prime/core/interfaces/banner.py` |
| `bangzen_prime/interfaces/cli.py` | `bangzen_prime/core/interfaces/cli.py` |
| `bangzen_prime/interfaces/dashboard.py` | `bangzen_prime/core/interfaces/dashboard.py` |
| `bangzen_prime/interfaces/demo.py` | `bangzen_prime/core/interfaces/demo.py` |
| `bangzen_prime/interfaces/ev_cli.py` | `bangzen_prime/core/interfaces/ev_cli.py` |
| `bangzen_prime/interfaces/execution_cli.py` | `bangzen_prime/core/interfaces/execution_cli.py` |
| `bangzen_prime/interfaces/intel_cli.py` | `bangzen_prime/core/interfaces/intel_cli.py` |
| `bangzen_prime/interfaces/soak.py` | `bangzen_prime/core/interfaces/soak.py` |
| `bangzen_prime/interfaces/test_logic.py` | `bangzen_prime/core/interfaces/test_logic.py` |
| `bangzen_prime/interfaces/wallet_cli.py` | `bangzen_prime/core/interfaces/wallet_cli.py` |
| `bangzen_prime/interfaces/ws_cli.py` | `bangzen_prime/core/interfaces/ws_cli.py` |
