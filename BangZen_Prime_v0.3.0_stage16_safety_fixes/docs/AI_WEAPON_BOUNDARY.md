# AI Manager: Analysis-Only Weapon Boundary

## Authority

The AI Manager is an evidence analyst and on-demand weapon selector. It is not a portfolio manager, trader, broker, wallet operator, or transaction executor.
It may inspect validated evidence and request zero or one analysis weapon when a specific evidence-backed trigger makes that analysis useful. The catalog is an allowlist, not a checklist. An empty selection is valid.

## Evidence handling

- Only validated, subject-matched, sufficiently fresh evidence may justify a weapon call.
- Missing, stale, partial, unavailable, or conflicting history remains explicitly uncertain.
- A weapon may investigate a concrete uncertainty; it cannot convert missing evidence into verified evidence.
- Favorable data may justify one independent confirmation tool. Suspicious data may justify one targeted forensic tool.
- Tool outputs remain advisory evidence and require provenance and validation before reuse.

## Outside AI Manager authority

The AI Manager must not access or manage balances/funds, calculate position sizing or financial exposure, produce buy/sell plans, set TP/SL/slippage/TWAP, authorize or construct transactions, sign, submit, broadcast, or make final financial decisions. Four financial/execution-adjacent tools are excluded from the AI-visible allowlist; their implementations are not deleted.

## Selection policy

Scenario entries in config/strategy_matrix.json are candidate sets, not mandatory call lists. Runtime integration must select at most one candidate based on the strongest validated trigger and available inputs. If no candidate is relevant or evidence is insufficient, it must not call a weapon.

## Integration status

This change updates configuration and adds regression tests/documentation. It does not yet prove every runtime LLM/provider call site loads and enforces these files. Runtime wiring and call-site audit are separate work and must fail closed if policy loading or validation fails.
