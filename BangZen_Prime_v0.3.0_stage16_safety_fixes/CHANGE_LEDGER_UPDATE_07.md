# Change Ledger — Update 07 (forward paper session)

## Added
- `execution/forward_session.py`: `ForwardPaperSession` connects accepted signals to paper
  orders, settlement, and the forward ledger in one cycle (`run_once`).
  - `open()` loads an existing ledger only if its frozen config hash matches. A different
    hash is refused, so one ledger never mixes configurations.
  - Lifecycle phase is read from `token_lifecycle` when the order is opened and kept in memory.
    After a restart, phases of orders opened earlier are "UNKNOWN". Phase is never taken from
    the close time.
  - Ledger is saved after every cycle.
- `paper_config_hash(...)`: SHA-256 of every setting that changes paper outcomes (risk limits,
  fee, slippage, daily-loss limit). Timedeltas are stored as whole seconds.
- `tests/unit/test_forward_session.py`: 6 tests.

## Changed
- `research/forward_paper.py`: lifecycle phases now use the repository names from
  `discovery.lifecycle.LifecyclePhase` (DISCOVERED ... UNKNOWN). Earlier draft names
  (pre_launch, mature, ...) were removed; they were not in the repo.
- `research/forward_paper.py`: `closed_at == opened_at` is now allowed. Zero holding time can
  happen when open and settle occur in the same tick. `closed_at < opened_at` is still refused.
- `execution/forward_recording.py`: `sync_closed_orders` accepts a function of the order for
  the lifecycle phase, in addition to a fixed string.
- `tests/unit/test_forward_paper.py`, `test_forward_recording.py`: phase names updated to match.

## Not done
- No scheduler or CLI command runs `ForwardPaperSession` yet. It is a library call.
- Phase is not persisted with the order, so it is lost on restart for orders opened earlier.
- Settlement is driven by `price_lookup`. Production price feeds are not connected here.
- A forward record is still empty until the session runs on real market data.

## Validation
- `scripts/run_tests.py` with httpx on PYTHONPATH: 991 passed, 0 failed, 0 errors, 0 skipped.
- `compileall`: passed.
- `check_unused_imports.py`: same 6 pre-existing findings; none in new code.
