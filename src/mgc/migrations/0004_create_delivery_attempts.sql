CREATE TABLE delivery_attempts (
    id TEXT PRIMARY KEY,
    delivery_id TEXT NOT NULL REFERENCES deliveries (id),
    attempt_number INTEGER NOT NULL,
    worker_id TEXT,
    claim_token TEXT,
    started_at TEXT,
    finished_at TEXT,
    outcome TEXT,
    http_status INTEGER,
    error TEXT
);

CREATE INDEX idx_delivery_attempts_delivery_id ON delivery_attempts (delivery_id);
