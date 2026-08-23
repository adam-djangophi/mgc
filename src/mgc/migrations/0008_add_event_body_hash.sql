ALTER TABLE events ADD COLUMN body_hash TEXT NOT NULL DEFAULT '';

CREATE UNIQUE INDEX idx_events_tenant_body_hash
    ON events (tenant_id, body_hash)
    WHERE body_hash <> '';
