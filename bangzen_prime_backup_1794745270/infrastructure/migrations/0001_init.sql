-- 0001: core persistence for tokens, pairs, prices, safety, signals, outbox, audit.
CREATE TABLE tokens (
  id TEXT PRIMARY KEY,
  chain TEXT NOT NULL,
  mint TEXT NOT NULL,
  symbol TEXT NOT NULL,
  name TEXT NOT NULL DEFAULT '',
  created_at TEXT NOT NULL,
  UNIQUE (chain, mint)
);
CREATE TABLE pairs (
  id TEXT PRIMARY KEY,
  token_id TEXT NOT NULL REFERENCES tokens(id),
  chain TEXT NOT NULL,
  pair_address TEXT NOT NULL,
  dex_id TEXT NOT NULL,
  price_usd TEXT NOT NULL,
  liquidity_usd TEXT NOT NULL,
  volume_24h_usd TEXT NOT NULL,
  observed_at TEXT NOT NULL,
  UNIQUE (chain, pair_address)
);
CREATE TABLE price_samples (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_id TEXT NOT NULL REFERENCES tokens(id),
  price_usd TEXT NOT NULL,
  observed_at TEXT NOT NULL
);
CREATE INDEX ix_price_samples_token ON price_samples (token_id, id);
CREATE TABLE safety_checks (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  token_id TEXT NOT NULL REFERENCES tokens(id),
  risk_score TEXT NOT NULL,
  rugged INTEGER NOT NULL CHECK (rugged IN (0, 1)),
  source TEXT NOT NULL,
  checked_at TEXT NOT NULL
);
CREATE TABLE signals (
  id TEXT PRIMARY KEY,
  token_id TEXT NOT NULL REFERENCES tokens(id),
  pair_id TEXT NOT NULL REFERENCES pairs(id),
  status TEXT NOT NULL CHECK (status IN ('ACCEPTED', 'REJECTED')),
  score TEXT NOT NULL,
  entry_price TEXT,
  stop_loss TEXT,
  take_profit TEXT,
  confidence TEXT,
  reasons TEXT NOT NULL,
  created_at TEXT NOT NULL,
  CHECK (status = 'REJECTED' OR (entry_price IS NOT NULL AND stop_loss IS NOT NULL
                                 AND take_profit IS NOT NULL AND confidence IS NOT NULL))
);
CREATE TABLE outbox (
  id TEXT PRIMARY KEY,
  event_name TEXT NOT NULL,
  payload TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('PENDING', 'PROCESSING', 'SENT', 'FAILED')),
  attempts INTEGER NOT NULL DEFAULT 0,
  available_at TEXT NOT NULL,
  lease_until TEXT,
  last_error TEXT,
  sent_at TEXT
);
CREATE INDEX ix_outbox_due ON outbox (status, available_at);
CREATE TABLE processed_events (
  subscriber TEXT NOT NULL,
  event_id TEXT NOT NULL,
  processed_at TEXT NOT NULL,
  PRIMARY KEY (subscriber, event_id)
);
CREATE TABLE audit_log (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  event_type TEXT NOT NULL,
  payload TEXT NOT NULL,
  occurred_at TEXT NOT NULL,
  prev_hash TEXT NOT NULL,
  hash TEXT NOT NULL UNIQUE
);
