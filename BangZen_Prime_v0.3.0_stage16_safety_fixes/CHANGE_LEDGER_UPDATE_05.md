# Change Ledger — Update 05 (operational resilience)

## Added
- `discovery/cooldown_store.py`: discovery cooldowns persisted to JSON as epoch expiries.
  Atomic writes (temp file, fsync, os.replace). Corrupt or unknown-format files mean "no
  cooldowns", which causes a re-scan only. A cooldown is a scheduling hint, not a trade gate.
- `core/resource_guard.py`: RSS reader (/proc) and memory status OK / OVER_LIMIT / UNKNOWN.
  UNKNOWN is never reported as OK.
- `core/log_files.py`: size-based rotating file logger with the same redaction and JSON format.
- `core/health.py`: read-only health report. HALTED > DEGRADED > OK. Unknown memory does not
  by itself degrade the status.
- `tests/unit/test_ops_resilience.py`: 23 tests.

## Updated
- `discovery/scanner.py`: optional `cooldown_store` and `epoch_clock`. Default None keeps the
  old behaviour. The monotonic clock is converted on load, so restarts are handled correctly.
- `core/supervisor.py`: optional exponential backoff (default off), optional memory limit
  (default off, skips non-order workers only when over limit), and a BACKOFF status. Existing
  tests were not changed.

## Not done
- No hard timeout per worker. Python threads cannot be killed safely, so a hung worker still
  blocks the cycle. This is a known gap.
- Health is a function, not a served endpoint. Wiring it to a CLI or a health file is a
  separate step.
- Memory limit reads VmRSS from /proc. Whether this works on a given Termux build is NOT
  verified here.
- Log rotation is size-based only. No time-based rotation.

## Validation
- `scripts/run_tests.py` with httpx on PYTHONPATH: 972 passed, 0 failed, 0 errors, 0 skipped.
- `compileall`: passed.
- `check_unused_imports.py`: same 6 pre-existing findings. None in new code.
