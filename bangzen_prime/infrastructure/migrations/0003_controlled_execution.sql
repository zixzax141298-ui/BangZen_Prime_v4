-- 0003: controlled chain-execution attempts (validation, simulation, optional broadcast).
CREATE TABLE chain_attempts (
  id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  mode TEXT NOT NULL CHECK (mode IN ('VALIDATE_ONLY', 'SIMULATE_ONLY', 'BROADCAST')),
  state TEXT NOT NULL CHECK (state IN
    ('VALIDATED', 'REJECTED', 'SIMULATED', 'SUBMITTED', 'CONFIRMED', 'FAILED', 'UNKNOWN', 'DROPPED')),
  input_mint TEXT NOT NULL,
  output_mint TEXT NOT NULL,
  in_amount TEXT NOT NULL,
  out_amount TEXT,
  provider TEXT,
  reason TEXT,
  signature TEXT,
  plan_expires_at TEXT,
  created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX ix_chain_attempts_state ON chain_attempts (state);
