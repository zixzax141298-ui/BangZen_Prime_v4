# BANGZEN PRIME — Lifecycle Weapon System

## Purpose and boundary

This policy maps each validated Solana token lifecycle phase to a small set of relevant
analysis/defensive capabilities. The selector chooses **zero or one** weapon. It is
deterministic and consumes only an `EvidencePackage` from
`ai_manager_contract.py`; it does not fetch data, call an LLM, mutate a blacklist,
calculate position size, issue BUY/SELL/TP/SL instructions, or execute transactions.

The phase itself must be supplied by the upstream lifecycle/evidence pipeline. This
module deliberately does not infer a phase from incomplete market snapshots. Unknown
phase, stale evidence, partial evidence, conflicting evidence, or absent evidence means
no weapon is selected.

## Lifecycle map

| Lifecycle phase | Primary purpose | Eligible analysis candidates (only when their exact evidence is VERIFIED and fresh) |
|---|---|---|
| UNKNOWN | Do not guess token age or state | None; observe upstream |
| PUMPFUN_LAUNCH | Detect coordinated launch buys and linked funders | `sequential_bundle_detector`, `sybil_adapter`, `honeypot_adapter` |
| BONDING_CURVE | Monitor coordinated buyers and curve-stage sell pressure | `sequential_bundle_detector`, `pre_dump_radar`, `sybil_adapter` |
| MIGRATION | Verify migration event, pool creation and liquidity continuity | `lp_sniper_adapter`, `pre_dump_radar`, `sybil_adapter` |
| RAYDIUM_POOL | Verify pool/LP ownership and token transaction simulation | `lp_sniper_adapter`, `honeypot_adapter`, `sybil_adapter` |
| RAYDIUM_EARLY | Detect early pool sell pressure, coordinated holders and large-wallet exits | `pre_dump_radar`, `sybil_adapter`, `kol_exit_adapter` |
| GROWTH | Check smart-wallet/large-wallet flows and cross-market activity | `kol_exit_adapter`, `cross_chain_radar`, `copycat_trap` |
| DISTRIBUTION | Prioritize liquidity drain, developer outflow and sell pressure | `pre_dump_radar`, `kol_exit_adapter`, `autopsy_engine` |
| REVIVAL | Test whether renewed activity resembles historical recovery or known failure patterns | `autopsy_engine`, `cross_chain_radar`, `copycat_trap` |

The phase policy declares evidence requirements and priorities in
`config/lifecycle_weapon_policy.json`. The priority is a deterministic selection
order, **not** a probability, profitability score, or proof that a weapon is healthy.

## Evidence contract

Evidence must pass `EvidencePackage.eligible_evidence`: matching subject, schema-valid
record, VERIFIED status, completeness 1.0, valid chronology, and caller-supplied freshness
budget. Every selected plan includes evidence IDs. Evidence types are intentionally
specific (for example `migration_event`, `pool_state`, `lp_ownership`,
`funding_graph`, `dev_wallet_flow`, and `swap_flow`). A generic market snapshot
cannot satisfy a more specific phase requirement.

The selector does not fabricate missing evidence or silently interpret provider errors
as clean results. No matching candidate means no tool call. The caller should record
the plan reason code and continue monitoring or escalate to deterministic Risk/Safety.

## Existing-module reality

This is a routing/selection layer, not a claim that every listed adapter is production
complete. The existing inventory identifies stubs/placeholders and missing modules.
In particular, the dormant-whale and sibling-token tracker were not found in the
audited main tree; the smart-money engine is a thin wrapper; and some adapter
implementations remain limited. Those are not silently substituted or represented as
implemented by this PR. A selected ID still requires a separately verified provider
adapter and runtime wiring before any actual tool invocation.

## Safety invariants

- Analysis allowlist only; execution and financial tools are rejected by policy parsing.
- Maximum selected weapons is exactly one; zero is valid.
- No credentials are passed to the selector or AI.
- No BUY/SELL, balance, sizing, TP/SL, slippage, TWAP, signing, submission, or broadcast
  capability is introduced.
- Risk/Safety remains deterministic and retains final veto.
- This PR does not alter existing strategy thresholds or enable live trading.

## Integration sequence

1. Land this isolated selector and its tests.
2. Build evidence producers for each phase using Helius WebSocket for live events and
   Helius HTTP history for bounded historical reconciliation; explicitly track coverage
   and gaps.
3. Verify each adapter's implementation and output contract before registering it for
   runtime invocation.
4. Integrate the selector behind the AI Manager boundary, with a hard runtime allowlist,
   one-call budget, timeout/rate limit, and audit trail.
5. Add historical replay/backtesting by phase, including fees, price impact, slippage,
   failed exits, and partial fills. Promote no strategy based on raw win rate alone;
   evaluate net expectancy, drawdown, tail loss, sample size, and out-of-sample stability.

## Rollback

Remove the selector/config integration and revert this additive PR. No database migration,
provider configuration, strategy threshold, or execution path is changed.
