CREATE TABLE delivery_outbox (
    id TEXT PRIMARY KEY,
    delivery_id TEXT NOT NULL UNIQUE REFERENCES deliveries (id),
    created_at TEXT NOT NULL,
    published_at TEXT,
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT NOT NULL,
    last_error TEXT
);

CREATE INDEX idx_delivery_outbox_pending
    ON delivery_outbox (published_at, next_attempt_at);
