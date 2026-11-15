CREATE TABLE token_lifecycle (
    chain TEXT NOT NULL CHECK (chain = 'solana'),
    mint TEXT NOT NULL CHECK (length(mint) BETWEEN 32 AND 44),
    phase TEXT NOT NULL CHECK (phase IN (
        'DISCOVERED', 'LAUNCH', 'EARLY_ACTIVITY', 'EXPANSION',
        'CONSOLIDATION', 'DECLINING', 'MIGRATING', 'CEX_LISTED',
        'INACTIVE', 'UNKNOWN'
    )),
    first_seen_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    last_observed_at TEXT NOT NULL,
    reason TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    PRIMARY KEY (chain, mint)
);

CREATE INDEX idx_token_lifecycle_phase_seen
    ON token_lifecycle (phase, last_seen_at);

CREATE TABLE token_lifecycle_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chain TEXT NOT NULL,
    mint TEXT NOT NULL,
    from_phase TEXT,
    to_phase TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    reason TEXT,
    evidence_json TEXT NOT NULL DEFAULT '{}',
    CHECK (from_phase IS NULL OR from_phase IN (
        'DISCOVERED', 'LAUNCH', 'EARLY_ACTIVITY', 'EXPANSION',
        'CONSOLIDATION', 'DECLINING', 'MIGRATING', 'CEX_LISTED',
        'INACTIVE', 'UNKNOWN'
    )),
    CHECK (to_phase IN (
        'DISCOVERED', 'LAUNCH', 'EARLY_ACTIVITY', 'EXPANSION',
        'CONSOLIDATION', 'DECLINING', 'MIGRATING', 'CEX_LISTED',
        'INACTIVE', 'UNKNOWN'
    ))
);

CREATE INDEX idx_token_lifecycle_events_mint_time
    ON token_lifecycle_events (chain, mint, observed_at, id);
