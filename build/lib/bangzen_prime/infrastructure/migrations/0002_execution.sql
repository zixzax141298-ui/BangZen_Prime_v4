-- 0002: paper execution orders and ledger. Pre-release: this file defines the schema as shipped.
CREATE TABLE orders (
  id TEXT PRIMARY KEY,
  idempotency_key TEXT NOT NULL UNIQUE,
  signal_id TEXT NOT NULL REFERENCES signals(id),
  token_id TEXT NOT NULL REFERENCES tokens(id),
  status TEXT NOT NULL CHECK (status IN
    ('NEW', 'FILLED', 'PARTIALLY_FILLED', 'REJECTED', 'TIMEOUT', 'CLOSED')),
  requested_units TEXT NOT NULL,
  filled_units TEXT NOT NULL DEFAULT '0',
  entry_price TEXT NOT NULL,
  fill_price TEXT,
  stop_loss TEXT NOT NULL,
  take_profit TEXT NOT NULL,
  entry_fee TEXT NOT NULL DEFAULT '0',
  exit_price TEXT,
  exit_fee TEXT,
  realized_pnl TEXT,
  created_at TEXT NOT NULL,
  closed_at TEXT
);
CREATE INDEX ix_orders_open ON orders (status);
CREATE TABLE ledger_entries (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id TEXT NOT NULL REFERENCES orders(id),
  kind TEXT NOT NULL CHECK (kind IN ('ENTRY_FEE', 'EXIT_FEE', 'REALIZED_PNL')),
  amount_quote TEXT NOT NULL,
  created_at TEXT NOT NULL
);
