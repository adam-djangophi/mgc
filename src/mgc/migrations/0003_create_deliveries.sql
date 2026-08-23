CREATE TABLE deliveries (
    id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL REFERENCES events (id),
    endpoint_id TEXT NOT NULL REFERENCES endpoints (id),
    tenant_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    attempt_count INTEGER NOT NULL DEFAULT 0,
    next_attempt_at TEXT,
    claimed_by TEXT,
    claim_token TEXT,
    claim_expires_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX idx_deliveries_tenant_id ON deliveries (tenant_id);
CREATE INDEX idx_deliveries_event_id ON deliveries (event_id);
CREATE INDEX idx_deliveries_endpoint_id ON deliveries (endpoint_id);
CREATE INDEX idx_deliveries_status_next_attempt ON deliveries (status, next_attempt_at);
