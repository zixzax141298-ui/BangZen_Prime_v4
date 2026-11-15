CREATE TABLE chain_history_signatures (
    address TEXT NOT NULL CHECK (length(address) BETWEEN 32 AND 44),
    signature TEXT NOT NULL CHECK (length(signature) BETWEEN 64 AND 88),
    slot INTEGER NOT NULL CHECK (slot >= 0),
    block_time INTEGER CHECK (block_time IS NULL OR block_time >= 0),
    transaction_error INTEGER NOT NULL CHECK (transaction_error IN (0, 1)),
    confirmation_status TEXT,
    memo TEXT,
    source TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    PRIMARY KEY (address, signature)
);

CREATE INDEX idx_chain_history_address_slot
    ON chain_history_signatures (address, slot DESC);

CREATE TABLE chain_history_checkpoints (
    address TEXT PRIMARY KEY CHECK (length(address) BETWEEN 32 AND 44),
    before_signature TEXT,
    last_signature TEXT,
    last_slot INTEGER CHECK (last_slot IS NULL OR last_slot >= 0),
    pages_fetched INTEGER NOT NULL DEFAULT 0 CHECK (pages_fetched >= 0),
    coverage_status TEXT NOT NULL CHECK (
        coverage_status IN ('NOT_STARTED', 'MORE_AVAILABLE', 'EXHAUSTED', 'FAILED')
    ),
    updated_at TEXT NOT NULL
);
