# Change Ledger: Stage 4 (partial), native loader guard (F7)

## Objective
Stop a `bangzen_native.py` planted in the working directory from being imported at startup.

## Scope
Only F7 from the audit. Not done: F6 (dependency lock with hashes, rustup and maturin pinning).
Those need network access, which this session does not have.

## Changed files
- `bangzen_prime/native/rust_bridge.py`: module loading moved into `_load_native()`. A module
  whose origin is inside the working directory is ignored and logged at ERROR. Python fallback is used.
- `tests/unit/test_rust_bridge_guard.py`: new test. A planted module in the working directory is
  ignored, and the Python implementation still returns the reviewed result.

## Compatibility
- Installed `bangzen_native` outside the working directory loads as before.
- A virtualenv inside the project directory would also be treated as "in the working directory" and
  ignored. The Python fallback runs, so this is safe but slower. Not seen in the Docker image, where
  the working directory is /app.

## Tests executed
- `tests.unit.test_rust_bridge_guard`: passes.
- Full suite (verification stub for httpx): 912 tests, 904 passed, 3 failed, 5 errors. Compared with
  Stage 2, the only status change is the new passing test. The 3 failures and 5 errors are the same
  pre-existing ones.

## Checks not run
- Full `tools/ci.py`: not green. Same pre-existing lint and type debt as Stage 2.

## Rollback
Restore the previous top-level `try: import bangzen_native` block and delete the new test.
