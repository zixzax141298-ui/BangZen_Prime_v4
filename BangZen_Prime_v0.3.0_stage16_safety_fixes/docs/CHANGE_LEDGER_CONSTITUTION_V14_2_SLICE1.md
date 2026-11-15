# Change ledger: constitution v14.2, migration slice 1

**Owner approval:** The owner directed adoption of BANGZEN_STRATEGIC_CONSTITUTION.md v14.2 as
mandatory and approved changing AI decision authority in writing (owner message, this session).
This record is the approval reference for the changes below.

**Scope of slice 1:** Remove AI from the entry path. AI is no longer a scan gate, a required
phase evidence item, or a paper-trade veto.

## Changed

| Area | Before | After |
|---|---|---|
| Scan (`use_cases.py`) | AI called on every scan; `AI_REJECTED` / `AI_UNAVAILABLE` could reject | AI not called in scan; `ai_brain`, `ai_mode`, `market_sentiment` parameters removed |
| Phase policy (`phase_policy.py`, `config/phase_policy.json`) | `ai` required for EARLY/GROWTH/MATURE and in `SAFETY_FLOOR` | `ai` removed from evidence and requirements |
| Policy loader | Accepted `ai` requirement | Refuses files that require `ai` (fails closed, operators must update) |
| Paper engine (`paper_trading.py`) | Optional `ai_gate` could veto an order | `ai_gate` removed |
| Demo (`demo.py`) | Offline AI stub wired into scan | Stub and wiring removed |
| Bootstrap (`bootstrap.py`) | Scan received AI brain and sentiment | Not passed to scan |

## Tests

- `tests/unit/test_phase_policy.py`: updated. AI absence no longer blocks entry; the policy cannot
  require `ai`.
- `tests/unit/test_constitution_v14_2.py`: new guards (7 tests) that fail if AI regains entry
  authority: scan signature, paper signature, `Evidence` fields, `SAFETY_FLOOR`, source tokens
  (`decision == "BUY"`, `AIBrain`, `ai_gate`, `ai_decision`) in the entry modules, shipped policy
  file, and refusal of an old policy file.
- Full suite: error set identical to baseline. The 12 remaining errors are all
  `ModuleNotFoundError: httpx` in this sandbox (network disabled). E2E and CLI tests also depend on
  `httpx` through `bootstrap` and did not run here.
- Smoke: demo and soak still complete with stubbed `httpx`.

## Not yet compliant (open, required for full v14.2)

1. `ai_brain.py`: SYSTEM_PROMPT still asks the model for `decision` (BUY/SKIP). This violates
   AI_RULES section 4 ("must not make BUY decisions"). Replace with a research-report schema.
2. `ai_commander.py`: returns a BUY recommendation and logs it as one. Convert to research output.
3. `controlled_execution.py` (live path, locked): still treats AI `BUY` as a pre-trade gate.
   Remove before any live discussion.
4. `ai_manager_contract.py`, `lifecycle_weapon_router.py`, `config/ai_tools.json`,
   `config/ai_tool_weapon_map.json`: AI-selected tools and "weapons" must be audited against
   constitution section 6 ("AI cannot issue trading commands") and replaced or removed.
5. No confirmed-event research queue, event persistence before enqueue, deduplication by snapshot
   hash, single-active-provider router with nine slots, research archive, reputation evaluator, or
   quarantine. These are SLOW PATH requirements and are not implemented.
6. Tests for items 1-5 are not written yet (AGENTS.md section 7).

## Rollback

Restore `docs/archive/governance_pre_v14.2/` for prior documents. Re-add `ai` to
`config/phase_policy.json` only together with a reverted `phase_policy.py`. Do not re-enable AI
entry gating without a new owner decision.
