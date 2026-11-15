-- Lifecycle phase captured when a paper order is opened by the forward paper session.
-- Written once per order (INSERT OR IGNORE). Phase is never inferred from close time.
CREATE TABLE forward_order_phase (
    order_id TEXT PRIMARY KEY REFERENCES orders(id),
    phase TEXT NOT NULL CHECK (phase IN (
        'DISCOVERED', 'LAUNCH', 'EARLY_ACTIVITY', 'EXPANSION',
        'CONSOLIDATION', 'DECLINING', 'MIGRATING', 'CEX_LISTED',
        'INACTIVE', 'UNKNOWN'
    )),
    recorded_at TEXT NOT NULL
);
